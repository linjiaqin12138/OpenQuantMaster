from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from tools.base.tool_result import ArtifactRef


@dataclass
class RunContext:
    pipeline_run_id: uuid.UUID
    inputs: dict[str, Any] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        return json.dumps(
            {
                "pipeline_run_id": str(self.pipeline_run_id),
                "inputs": self.inputs,
                "outputs": self.outputs,
                "artifacts": [a.model_dump() for a in self.artifacts],
                "metadata": self.metadata,
            },
            default=str,
        )
