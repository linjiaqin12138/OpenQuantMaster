from __future__ import annotations

from pydantic import BaseModel, Field


class AgentTask(BaseModel):
    skill_path: str
    task_description: str
    previous_artifact_path: str
    output_dir: str
    pipeline_run_id: str
    timeout_sec: int = Field(default=120, ge=1)
