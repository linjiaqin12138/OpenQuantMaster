from __future__ import annotations

from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Self


@dataclass
class Error:
    code: str
    message: str
    exception: Exception | None = None


class AppError(Exception):
    """An already categorized failure raised by application code.

    One generic exception for the whole application: the ``code`` carries the
    classification (``provider_rejected``, ``provider_unavailable``, ...), never
    the exception class. It is not tied to one layer or one integration.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Result:
    success: bool
    data: Any = None
    error: Error | None = None

    @classmethod
    def from_error(
        cls,
        code: str,
        message: str,
        exception: Exception | None = None,
    ) -> Self:
        return cls(
            success=False,
            error=Error(code=code, message=message, exception=exception),
        )


@dataclass
class ServiceResult(Result):
    duration_seconds: float = 0.0


def as_call_result(
    func: Callable[..., Any],
    *,
    map_error: Callable[[Exception], Error | None] | None = None,
) -> Callable[..., Any]:
    """Wrap a provider call so ordinary failures come back as a ``Result``.

    An :class:`AppError` keeps its own code and message. A mapper returning
    ``None`` means "no specific classification" and the failure is reported
    with the ``unknown`` code. Unexpected exceptions raised outside a provider
    call keep propagating to the caller.
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Result:
        try:
            data = await func(*args, **kwargs)
            return Result(success=True, data=data)
        except AppError as exc:
            return Result(
                success=False,
                error=Error(code=exc.code, message=exc.message, exception=exc),
            )
        except Exception as exc:
            error = map_error(exc) if map_error is not None else None
            if error is None:
                error = Error(code="unknown", message=str(exc), exception=exc)
            return Result(success=False, error=error)

    return wrapper
