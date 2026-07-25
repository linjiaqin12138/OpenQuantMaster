from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from runtime.agent_gateway.agent_driver import AgentDriver
from runtime.agent_gateway.agent_task import AgentTask
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult


class AgentToolInput(BaseModel):
    skill: str
    task_description: str
    timeout_sec: int | None = Field(default=None, ge=1)
    pipeline_run_id: str | None = None


class AgentToolOutput(BaseModel):
    success: bool
    report_artifact: str
    summary: str


class AgentTool(BaseTool):
    name: ClassVar[str] = "agent_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "agent_gateway"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = AgentToolInput
    output_model: ClassVar[type[BaseModel]] = AgentToolOutput

    def __init__(self, agent_driver: AgentDriver, artifacts_path: Path) -> None:
        self._agent_driver = agent_driver
        self._artifacts_path = artifacts_path

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        run_id = inputs.get("pipeline_run_id")
        if not run_id:
            run_id = str(uuid.uuid4())

        previous_artifact_path = str(
            self._artifacts_path / run_id / "generate_data" / "demo_data.json"
        )
        output_dir = str(self._artifacts_path / run_id / "agent_analyze")

        task = AgentTask(
            skill_path=inputs["skill"],
            task_description=inputs["task_description"],
            previous_artifact_path=previous_artifact_path,
            output_dir=output_dir,
            pipeline_run_id=run_id,
            timeout_sec=inputs.get("timeout_sec") or self._agent_driver.default_timeout_sec,
        )

        result = await self._agent_driver.run(task)

        if not result.success:
            return ToolResult(
                success=False,
                data={},
                artifacts=[],
                error=result.error or "Agent execution failed",
            )

        report_path = self._artifacts_path / run_id / "agent_analyze" / "report.md"
        report_content = report_path.read_text(encoding="utf-8")
        sha256 = hashlib.sha256(report_content.encode("utf-8")).hexdigest()
        relative_path = str(report_path.relative_to(self._artifacts_path))

        artifact = ArtifactRef(
            name="report.md",
            mime_type="text/markdown",
            relative_path=relative_path,
            sha256=sha256,
            content=report_content,
        )

        output = self.output_model(
            success=True,
            report_artifact="report.md",
            summary=result.summary or "",
        )

        return ToolResult(
            success=True,
            data=output.model_dump(),
            artifacts=[artifact],
        )
