from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, Field

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ToolResult


class EchoInput(BaseModel):
    message: str = Field(..., min_length=1)
    repeat: int = Field(default=1, ge=1)


class EchoOutput(BaseModel):
    echoed: str


class EchoTool(BaseTool):
    name: ClassVar[str] = "echo_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "demo"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = EchoInput
    output_model: ClassVar[type[BaseModel]] = EchoOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        message = inputs["message"]
        repeat = inputs.get("repeat", 1)
        echoed = " ".join([message] * repeat)
        return ToolResult(
            success=True,
            data=self.output_model(echoed=echoed).model_dump(),
            artifacts=[],
            error=None,
            cost_usd=0.0,
        )
