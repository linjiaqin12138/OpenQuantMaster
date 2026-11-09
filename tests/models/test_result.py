import pytest

from src.models.result import AppError, Error, Result, as_call_result


@pytest.mark.unit
@pytest.mark.asyncio
async def test_successful_call_returns_the_data():
    async def _call() -> str:
        return "data"

    result = await as_call_result(_call)()

    assert isinstance(result, Result)
    assert result.success is True
    assert result.data == "data"
    assert result.error is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_app_error_keeps_its_own_code():
    async def _call() -> str:
        raise AppError("provider_rejected", "the provider rejected the call")

    result = await as_call_result(_call)()

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_rejected"
    assert result.error.message == "the provider rejected the call"
    assert isinstance(result.error.exception, AppError)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_app_error_is_not_reclassified_by_the_mapper():
    async def _call() -> str:
        raise AppError("provider_rejected", "rejected")

    def _map_error(exc: Exception) -> Error:
        return Error(code="provider_unavailable", message=str(exc))

    result = await as_call_result(_call, map_error=_map_error)()

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_rejected"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_other_exceptions_use_the_mapper():
    async def _call() -> str:
        raise TimeoutError("too slow")

    def _map_error(exc: Exception) -> Error | None:
        if isinstance(exc, TimeoutError):
            return Error(code="provider_timeout", message=str(exc), exception=exc)
        return None

    result = await as_call_result(_call, map_error=_map_error)()

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_timeout"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unclassified_exceptions_fall_back_to_unknown():
    async def _call() -> str:
        raise RuntimeError("boom")

    result = await as_call_result(_call)()

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "unknown"
    assert result.error.message == "boom"
