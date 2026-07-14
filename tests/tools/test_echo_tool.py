import pytest

from pydantic import ValidationError

from tools.base.tool_registry import ToolRegistry
from tools.demo.echo_tool import EchoTool


@pytest.mark.unit
def test_registry_discovers_echo_tool():
    import tools

    registry = ToolRegistry()
    count = registry.discover(tools)
    assert count == 1
    assert registry.list_tools() == ["echo_tool"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_echo_tool_repeats_message():
    tool = EchoTool()
    result = await tool.execute({"message": "hi", "repeat": 3})
    assert result.success is True
    assert result.data == {"echoed": "hi hi hi"}
    assert result.error is None
    assert result.cost_usd == 0.0
    assert result.duration_seconds >= 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_echo_tool_default_repeat():
    tool = EchoTool()
    result = await tool.execute({"message": "hello"})
    assert result.data == {"echoed": "hello"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_echo_tool_rejects_invalid_repeat():
    tool = EchoTool()
    result = await tool.execute({"message": "hello", "repeat": 0})
    assert result.success is False
    assert "repeat" in result.error.lower()


@pytest.mark.unit
def test_echo_tool_input_model_rejects_missing_message():
    tool = EchoTool()
    with pytest.raises(ValidationError):
        tool.input_model(**{})
