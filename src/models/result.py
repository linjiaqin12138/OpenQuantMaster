from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class Error(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    code: str
    message: str
    exception: Exception | None = None


class OperationResult(BaseModel):
    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    error: Error | None = None

    @classmethod
    def from_error(
        cls,
        code: str,
        msg: str,
        exception: Exception | None = None,
    ) -> Self:
        return cls(
            success=False,
            error=Error(code=code, message=msg, exception=exception),
        )
