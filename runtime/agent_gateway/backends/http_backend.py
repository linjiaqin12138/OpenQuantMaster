from __future__ import annotations

from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask

from .base import BaseBackend


class HttpBackend(BaseBackend):
    async def run(self, task: AgentTask) -> AgentResult:
        raise NotImplementedError("HTTP backend is not implemented")
