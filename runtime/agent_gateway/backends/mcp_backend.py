from __future__ import annotations

from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask

from .base import BaseBackend


class McpBackend(BaseBackend):
    async def run(self, task: AgentTask) -> AgentResult:
        raise NotImplementedError("MCP backend is not implemented")
