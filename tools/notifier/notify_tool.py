from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from runtime.notifier.base import Notifier
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ToolResult


class NotifyToolInput(BaseModel):
    subject: str
    body: str
    channels: list[str] = Field(default_factory=list)


class NotifyToolOutput(BaseModel):
    success: bool
    results: dict[str, Any]


class NotifyTool(BaseTool):
    name: ClassVar[str] = "notify_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "notification"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = NotifyToolInput
    output_model: ClassVar[type[BaseModel]] = NotifyToolOutput

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    @staticmethod
    def _is_failure(value: Any) -> bool:
        if value is False:
            return True
        if isinstance(value, dict):
            return value.get("success") is False
        if isinstance(value, str):
            return (
                value.startswith("error:")
                or value == "missing token"
                or value == "not_implemented"
            )
        return False

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        subject = inputs["subject"]
        body = inputs["body"]
        channels: list[str] = inputs.get("channels", [])

        results = dict(await self._notifier.send(subject, body))

        for channel in channels:
            if channel not in results:
                results[channel] = "not_implemented"

        if not results:
            success = True
        else:
            success = not all(self._is_failure(value) for value in results.values())

        output = self.output_model(success=success, results=results)
        return ToolResult(success=success, data=output.model_dump())
