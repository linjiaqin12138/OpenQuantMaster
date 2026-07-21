from __future__ import annotations

from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.agent_gateway.backends.base import BaseBackend
from runtime.agent_gateway.backends.cli_backend import CliBackend
from runtime.agent_gateway.backends.http_backend import HttpBackend
from runtime.agent_gateway.backends.mcp_backend import McpBackend
from runtime.config_loader import AgentConfig


class AgentDriver:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config
        if config.tool_callback == "cli":
            self._backend: BaseBackend = CliBackend(config)
        elif config.tool_callback == "mcp":
            self._backend = McpBackend(config)
        elif config.tool_callback == "http":
            self._backend = HttpBackend(config)
        else:
            raise ValueError(f"Unknown tool_callback: {config.tool_callback}")

    async def run(self, task: AgentTask) -> AgentResult:
        return await self._backend.run(task)
