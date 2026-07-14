import pytest

from tools import demo
from tools.base import ArtifactRef, BaseTool, ToolNotFoundError, ToolRegistry, ToolResult


def test_base_imports():
    assert ArtifactRef is not None
    assert BaseTool is not None
    assert ToolRegistry is not None
    assert ToolResult is not None
    assert ToolNotFoundError is not None
    assert demo is not None
