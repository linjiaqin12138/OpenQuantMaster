from __future__ import annotations

import asyncio
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, ConfigDict, Field

from tools.base.base_tool import BaseTool
from tools.base.tool_registry import ToolNotFoundError, ToolRegistry
from tools.base.tool_result import ToolResult

logger = structlog.get_logger()


class ParallelCall(BaseModel):
    tool: str = Field(..., min_length=1)
    inputs: dict[str, Any] = Field(default_factory=dict)


class ParallelInput(BaseModel):
    calls: dict[str, ParallelCall] = Field(..., min_length=1)
    pipeline_run_id: str | None = None


class ParallelOutput(BaseModel):
    """Flat dynamic keys: { <call_key>: <serialized ToolResult> }.

    Extra-allow so the runner's ``output_model(**result.data)`` validation
    accepts arbitrary call keys and downstream stages can use ``$stage.key``.
    """

    model_config = ConfigDict(extra="allow")


class ParallelTool(BaseTool):
    """Generic parallel orchestrator: run registered tools concurrently.

    The instance needs the live ToolRegistry, so it is skipped by
    ``ToolRegistry.discover`` (no-arg construction) and registered explicitly
    in ``runtime/bootstrap.py`` and ``runtime/cli.py`` — same pattern as
    ``NotifyTool``/``AgentTool``.
    """

    name: ClassVar[str] = "parallel_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "runtime"
    input_model: ClassVar[type[BaseModel]] = ParallelInput
    output_model: ClassVar[type[BaseModel]] = ParallelOutput

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        params = ParallelInput(**inputs)
        run_id = params.pipeline_run_id

        for key, call in params.calls.items():
            if call.tool == self.name:
                return ToolResult(
                    success=False,
                    error=f"Recursive call rejected: '{key}' targets {self.name}",
                )
            try:
                self._registry.get(call.tool)
            except ToolNotFoundError:
                return ToolResult(
                    success=False,
                    error=f"Call '{key}' targets unregistered tool '{call.tool}'",
                )

        async def run_call(key: str, call: ParallelCall) -> tuple[str, ToolResult]:
            tool = self._registry.get(call.tool)
            child_inputs = dict(call.inputs)
            if run_id and "pipeline_run_id" in tool.input_model.model_fields:
                child_inputs["pipeline_run_id"] = run_id
            logger.info("parallel.call.started", key=key, tool=call.tool)
            result = await tool.execute(child_inputs)
            logger.info("parallel.call.completed", key=key, tool=call.tool, success=result.success)
            return key, result

        pairs = await asyncio.gather(*(run_call(key, call) for key, call in params.calls.items()))
        results = dict(pairs)

        failures = {k: r.error or "Unknown tool error" for k, r in results.items() if not r.success}
        data = {key: result.model_dump() for key, result in results.items()}
        cost = sum(r.cost_usd for r in results.values())
        if failures:
            summary = "; ".join(f"{k}: {err}" for k, err in failures.items())
            return ToolResult(success=False, data=data, error=f"Child calls failed: {summary}", cost_usd=cost)
        return ToolResult(success=True, data=data, cost_usd=cost)
