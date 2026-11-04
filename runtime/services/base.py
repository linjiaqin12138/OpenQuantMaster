from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel, Field


class ServiceResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    duration_seconds: float = 0.0


class BaseService(ABC):
    """Orchestration unit with explicit Pydantic I/O. No Click; no process lifecycle."""

    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    async def run(self, inputs: dict[str, Any]) -> ServiceResult:
        started = time.perf_counter()
        try:
            parsed = self.input_model(**inputs)
            result = await self._run(parsed)
            if result.success:
                self.output_model(**result.data)
        except Exception as exc:
            return ServiceResult(
                success=False,
                data={},
                error=str(exc),
                duration_seconds=time.perf_counter() - started,
            )
        result.duration_seconds = time.perf_counter() - started
        return result

    @abstractmethod
    async def _run(self, inputs: BaseModel) -> ServiceResult:
        """Subclasses orchestrate operations and/or other services here."""
