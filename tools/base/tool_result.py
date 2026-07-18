from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ArtifactRef(BaseModel):
    name: str
    mime_type: str
    relative_path: str
    sha256: str
    content: str | None = Field(default=None, repr=False)


class ToolResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    error: str | None = None
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
