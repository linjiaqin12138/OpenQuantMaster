from __future__ import annotations

from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig

from .base import STAGE_SYSTEM_PROMPT, AdapterCommand, BaseAdapter, agent_env, build_prompt


class ClaudeAdapter(BaseAdapter):
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        argv = [
            self._config.default_cli,
            *self._config.headless_args,
            "--allowed-tools",
            "Read,Write,Edit,Bash,Skill",
            "--append-system-prompt",
            STAGE_SYSTEM_PROMPT,
            "-p",
            build_prompt(task),
        ]
        return AdapterCommand(argv=argv, env=agent_env(task))
