from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult


class DemoDataInput(BaseModel):
    topic: str
    pipeline_run_id: str | None = None


class DemoDataOutput(BaseModel):
    topic: str
    rows: int
    artifact: str


class DemoDataTool(BaseTool):
    name: ClassVar[str] = "demo_data_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "demo"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = DemoDataInput
    output_model: ClassVar[type[BaseModel]] = DemoDataOutput

    def __init__(self, artifacts_path: Path | str = "artifacts") -> None:
        self._artifacts_path = Path(artifacts_path)

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        run_id = inputs.get("pipeline_run_id")
        if not run_id:
            run_id = str(uuid.uuid4())

        topic = inputs["topic"]
        data = [
            {"signal": "momentum", "value": 0.65},
            {"signal": "volume", "value": 0.42},
            {"signal": "sentiment", "value": 0.71},
        ]
        payload = {"topic": topic, "data": data}

        artifact_dir = self._artifacts_path / run_id / "generate_data"
        artifact_dir.mkdir(parents=True, exist_ok=True)

        artifact_path = artifact_dir / "demo_data.json"
        content = json.dumps(payload, indent=2)
        artifact_path.write_text(content, encoding="utf-8")

        relative_path = str(artifact_path.relative_to(self._artifacts_path))
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        artifact = ArtifactRef(
            name="demo_data.json",
            mime_type="application/json",
            relative_path=relative_path,
            sha256=sha256,
            content=content,
        )

        output = self.output_model(
            topic=topic,
            rows=len(data),
            artifact=relative_path,
        )

        return ToolResult(
            success=True,
            data=output.model_dump(),
            artifacts=[artifact],
        )
