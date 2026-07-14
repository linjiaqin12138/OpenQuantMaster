from __future__ import annotations

import inspect
import pkgutil
from types import ModuleType
from typing import Type

from .base_tool import BaseTool


class ToolNotFoundError(KeyError):
    pass


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if not isinstance(tool, BaseTool):
            raise TypeError(f"Expected BaseTool, got {type(tool)}")
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ToolNotFoundError(f"Tool '{name}' not found")
        return self._tools[name]

    def list_tools(self) -> list[str]:
        return sorted(self._tools.keys())

    def discover(self, package: ModuleType) -> int:
        """Walk package tree and instantiate concrete BaseTool subclasses."""
        count = 0
        prefix = package.__name__ + "."
        for _, modname, ispkg in pkgutil.walk_packages(
            path=package.__path__, prefix=prefix, onerror=lambda name: None
        ):
            if ispkg:
                continue
            try:
                module = __import__(modname, fromlist=[""])
            except Exception:
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (
                    issubclass(obj, BaseTool)
                    and obj is not BaseTool
                    and not getattr(obj, "__abstractmethods__", False)
                ):
                    try:
                        instance = obj()
                        self.register(instance)
                        count += 1
                    except Exception:
                        continue
        return count
