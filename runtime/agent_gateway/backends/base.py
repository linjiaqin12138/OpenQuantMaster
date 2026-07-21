from __future__ import annotations

from abc import ABC, abstractmethod

from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig


class BaseBackend(ABC):
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentResult:
        ...
