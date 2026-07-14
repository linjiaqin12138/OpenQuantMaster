from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from .tool_result import ToolResult


class BaseTool(ABC):
    name: ClassVar[str]
    version: ClassVar[str]
    capability: ClassVar[str]
    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]
    fallback_tools: ClassVar[list[str]] = []
    cost_estimate_usd: ClassVar[float] = 0.0

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.input_model.model_json_schema()

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.output_model.model_json_schema()

    async def execute(self, inputs: dict[str, Any]) -> ToolResult:
        """Validate inputs, time subclass _execute, and fill duration_seconds."""
        started = time.perf_counter()
        try:
            self.input_model(**inputs)
            result = await self._execute(inputs)
        except Exception as exc:
            return ToolResult(
                success=False,
                data={},
                artifacts=[],
                error=str(exc),
                cost_usd=0.0,
                duration_seconds=time.perf_counter() - started,
            )
        result.duration_seconds = time.perf_counter() - started
        return result

    @abstractmethod
    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        """Subclasses implement the actual tool logic here."""
