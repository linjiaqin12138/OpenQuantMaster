from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel

from runtime.services.echo_service import EchoInput, EchoOutput, EchoService
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ToolResult

__all__ = ["EchoInput", "EchoOutput", "EchoTool"]


class EchoTool(BaseTool):
    """Transitional pipeline adapter: delegates to EchoService."""

    name: ClassVar[str] = "echo_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "demo"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = EchoInput
    output_model: ClassVar[type[BaseModel]] = EchoOutput

    def __init__(self) -> None:
        self._service = EchoService()

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        result = await self._service.run(inputs)
        return ToolResult(
            success=result.success,
            data=result.data,
            artifacts=[],
            error=result.error,
            cost_usd=0.0,
        )
