from __future__ import annotations

from pydantic import BaseModel


class AgentResult(BaseModel):
    success: bool
    report_artifact: str | None = None
    summary: str | None = None
    error: str | None = None
