from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, ClassVar

from pydantic import BaseModel

from src.models.result import Error, OperationResult

ServiceError = Error


class ServiceResult(OperationResult):
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
            result = ServiceResult.from_error("unhandled_exception", str(exc), exc)
            result.duration_seconds = time.perf_counter() - started
            return result
        result.duration_seconds = time.perf_counter() - started
        return result

    @abstractmethod
    async def _run(self, inputs: BaseModel) -> ServiceResult:
        """Subclasses orchestrate operations and/or other services here."""
