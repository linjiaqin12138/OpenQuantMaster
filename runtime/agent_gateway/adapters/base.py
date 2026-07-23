from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from runtime.agent_gateway.agent_task import AgentTask

STAGE_SYSTEM_PROMPT = (
    "You are running as a stage in an OpenQuantMaster pipeline. "
    "Write your final report to $OQM_OUTPUT_DIR/report.md and end it with "
    "a line: <!-- summary: <one-sentence summary> -->."
)


@dataclass(frozen=True)
class AdapterCommand:
    argv: list[str]
    env: dict[str, str]
    cwd: str | None = None


def agent_env(task: AgentTask) -> dict[str, str]:
    return {
        "OQM_RUN_ID": task.pipeline_run_id,
        "OQM_OUTPUT_DIR": task.output_dir,
    }


def build_prompt(task: AgentTask) -> str:
    skill_name = Path(task.skill_path).stem
    return (
        f"加载 skill '{skill_name}'，阅读上一阶段产物 {task.previous_artifact_path}，"
        f"完成任务：{task.task_description}\n"
        "把最终报告写入 $OQM_OUTPUT_DIR/report.md，"
        "并在末尾加入一行：<!-- summary: 一句话摘要 -->"
    )


class BaseAdapter(ABC):
    @abstractmethod
    def compose_command(self, task: AgentTask) -> AdapterCommand:
        """Build the native argv/env/cwd for one headless Agent invocation."""
