from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel, ValidationError

from src.models.result import Error, ServiceResult

InputsT = TypeVar("InputsT", bound=BaseModel)
OutputsT = TypeVar("OutputsT", bound=BaseModel)


class BaseUseCase(ABC, Generic[InputsT, OutputsT]):
    """One complete application action behind a standard ``run()`` method.

    ``run()`` is the standard action boundary: it validates the request against
    the UseCase-owned Input model, calls ``_run()`` with the typed model,
    validates a successful result against the UseCase-owned Output model,
    normalizes the returned data, and records the duration. It may also add
    logging or tracing.

    It does not convert arbitrary exceptions into Results: unexpected failures
    keep propagating to the protocol layer.
    """

    input_model: ClassVar[type[BaseModel]]
    output_model: ClassVar[type[BaseModel]]

    async def run(self, inputs: InputsT | dict[str, Any]) -> ServiceResult:
        try:
            parsed = self.input_model.model_validate(inputs)
        except ValidationError as exc:
            return ServiceResult.from_error("invalid_input", _format_validation_error(exc))

        started = time.perf_counter()
        try:
            result = await self._run(parsed)
        finally:
            duration_seconds = time.perf_counter() - started

        if not result.success:
            result.duration_seconds = duration_seconds
            return result

        try:
            output = self.output_model.model_validate(result.data)
        except ValidationError as exc:
            return ServiceResult.from_error(
                "invalid_output",
                _format_validation_error(exc),
                exc,
            )
        return ServiceResult(
            success=True,
            data=output.model_dump(mode="json"),
            duration_seconds=duration_seconds,
        )

    @abstractmethod
    async def _run(self, inputs: InputsT) -> ServiceResult:
        """Application logic of this action."""


def provider_failure(
    error: Error | None,
    *,
    codes: Mapping[str, str],
    default: str,
) -> ServiceResult:
    """Map a provider error code onto the owning service's error contract.

    Only explicitly listed codes are special-cased; every other code - known,
    unknown, or added later - falls back to ``default``.
    """
    if error is None:
        return ServiceResult.from_error(default, "The operation could not be completed")
    code = codes.get(error.code, default)
    return ServiceResult.from_error(code, error.message, error.exception)


def _format_validation_error(exc: ValidationError) -> str:
    details = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in exc.errors()
    )
    return details or "Invalid input"
