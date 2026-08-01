import asyncio
import time
from typing import Any, ClassVar

import pytest
from pydantic import BaseModel

from tools.base.base_tool import BaseTool
from tools.base.tool_registry import ToolRegistry
from tools.base.tool_result import ToolResult
from tools.runtime.parallel_tool import ParallelTool


class StubInput(BaseModel):
    value: str = "ok"
    pipeline_run_id: str | None = None


class StubOutput(BaseModel):
    value: str


class FastTool(BaseTool):
    name: ClassVar[str] = "fast_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "demo"
    input_model: ClassVar[type[BaseModel]] = StubInput
    output_model: ClassVar[type[BaseModel]] = StubOutput

    def __init__(self) -> None:
        self.received_inputs: dict[str, Any] = {}

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        self.received_inputs = dict(inputs)
        return ToolResult(success=True, data={"value": inputs.get("value", "ok")}, cost_usd=0.01)


class SlowTool(FastTool):
    name: ClassVar[str] = "slow_tool"

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        await asyncio.sleep(0.2)
        return await super()._execute(inputs)


class FailingTool(FastTool):
    name: ClassVar[str] = "failing_tool"

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        return ToolResult(success=False, error="boom")


@pytest.fixture
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(FastTool())
    reg.register(SlowTool())
    reg.register(FailingTool())
    return reg


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_aggregates_results_by_key(registry):
    tool = ParallelTool(registry=registry)
    result = await tool.execute(
        {
            "calls": {
                "a": {"tool": "fast_tool", "inputs": {"value": "hello"}},
                "b": {"tool": "fast_tool", "inputs": {"value": "world"}},
            }
        }
    )

    assert result.success is True
    assert result.data["a"]["success"] is True
    assert result.data["a"]["data"]["value"] == "hello"
    assert result.data["b"]["data"]["value"] == "world"
    assert result.cost_usd == pytest.approx(0.02)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_runs_calls_concurrently(registry):
    tool = ParallelTool(registry=registry)
    started = time.perf_counter()
    result = await tool.execute(
        {
            "calls": {
                "a": {"tool": "slow_tool"},
                "b": {"tool": "slow_tool"},
            }
        }
    )
    elapsed = time.perf_counter() - started

    assert result.success is True
    assert elapsed < 0.35  # sequential would take >= 0.4s


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_rejects_recursion(registry):
    tool = ParallelTool(registry=registry)
    registry.register(tool)
    result = await tool.execute(
        {"calls": {"self": {"tool": "parallel_tool", "inputs": {}}}}
    )

    assert result.success is False
    assert "Recursive" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_rejects_unregistered_tool(registry):
    tool = ParallelTool(registry=registry)
    result = await tool.execute(
        {"calls": {"ghost": {"tool": "missing_tool", "inputs": {}}}}
    )

    assert result.success is False
    assert "ghost" in result.error
    assert "missing_tool" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_fails_when_any_child_fails(registry):
    tool = ParallelTool(registry=registry)
    result = await tool.execute(
        {
            "calls": {
                "good": {"tool": "fast_tool"},
                "bad": {"tool": "failing_tool"},
            }
        }
    )

    assert result.success is False
    assert "bad" in result.error
    assert "boom" in result.error
    # 失败时仍返回各 child 的序列化结果
    assert result.data["good"]["success"] is True
    assert result.data["bad"]["success"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_parallel_forwards_pipeline_run_id(registry):
    fast = registry.get("fast_tool")
    assert isinstance(fast, FastTool)

    tool = ParallelTool(registry=registry)
    result = await tool.execute(
        {
            "calls": {"a": {"tool": "fast_tool"}},
            "pipeline_run_id": "run-123",
        }
    )

    assert result.success is True
    assert fast.received_inputs["pipeline_run_id"] == "run-123"
