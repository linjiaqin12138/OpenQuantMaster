from __future__ import annotations

from runtime.agent_gateway.adapters.base import BaseAdapter
from runtime.agent_gateway.adapters.claude_adapter import ClaudeAdapter
from runtime.agent_gateway.adapters.codex_adapter import CodexAdapter
from runtime.agent_gateway.adapters.generic_adapter import GenericAdapter
from runtime.agent_gateway.adapters.kimi_adapter import KimiAdapter
from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.agent_gateway.backends.base import BaseBackend
from runtime.agent_gateway.backends.cli_backend import CliBackend
from runtime.config_loader import AgentConfig

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "kimi": KimiAdapter,
    "generic": GenericAdapter,
}


class AgentDriver:
    def __init__(self, config: AgentConfig) -> None:
        adapter_cls = _ADAPTERS.get(config.adapter)
        if adapter_cls is None:
            raise ValueError(f"Unknown agent adapter: {config.adapter}")
        self._config = config
        self._backend: BaseBackend = CliBackend(config, adapter_cls(config))

    @property
    def default_timeout_sec(self) -> int:
        return self._config.timeout_sec

    async def run(self, task: AgentTask) -> AgentResult:
        return await self._backend.run(task)
