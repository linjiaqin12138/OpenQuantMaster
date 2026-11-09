from typing import Any

import pytest

from src.composition import build_ohlcv_service
from src.config import AppConfig
from src.models.result import Error, Result

BAR = {
    "timestamp": "2026-01-01T00:00:00Z",
    "open": 100.0,
    "high": 110.0,
    "low": 90.0,
    "close": 105.0,
    "volume": 1000.0,
}


def _provider(data: list[dict[str, Any]]):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=True, data=data)

    return _call


def _failing_provider(code: str):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=False, error=Error(code=code, message="provider failed"))

    return _call


def _app_config(**providers: Any) -> AppConfig:
    return AppConfig.model_validate({"providers": providers})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_returns_normalized_bars(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _provider([BAR]),
    )

    service = build_ohlcv_service(_app_config())
    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h", "limit": 1}
    )

    assert result.success is True
    assert result.data["symbol"] == "BTCUSDT"
    assert result.data["rows"] == 1
    assert result.data["bars"][0]["close"] == 105.0
    assert result.data["bars"][0]["timestamp"] == "2026-01-01T00:00:00Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_maps_a_provider_outage(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _failing_provider("provider_unavailable"),
    )

    service = build_ohlcv_service(_app_config())
    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h"}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "market_data_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_maps_a_provider_rejection(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _failing_provider("provider_rejected"),
    )

    service = build_ohlcv_service(_app_config())
    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h"}
    )

    assert result.error is not None
    assert result.error.code == "market_data_rejected"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_maps_an_unknown_provider_failure(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _failing_provider("unknown"),
    )

    service = build_ohlcv_service(_app_config())
    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h"}
    )

    assert result.error is not None
    assert result.error.code == "market_data_failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_rejects_an_invalid_request():
    service = build_ohlcv_service(_app_config())

    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "forex", "interval": "1h"}
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert "market" in result.error.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_enforces_the_limit_bound():
    service = build_ohlcv_service(_app_config())

    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h", "limit": 5001}
    )

    assert result.error is not None
    assert result.error.code == "invalid_input"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_bars_rejects_a_source_outside_its_market():
    service = build_ohlcv_service(_app_config())

    result = await service.fetch_bars(
        {
            "symbol": "BTCUSDT",
            "market": "crypto",
            "interval": "1h",
            "source": "akshare",
        }
    )

    assert result.error is not None
    assert result.error.code == "unsupported_source"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_unsupported_venue_is_reported_as_an_unsupported_market():
    service = build_ohlcv_service(
        _app_config(binance={"exchange": "kraken", "product": "spot"})
    )

    result = await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h"}
    )

    assert result.error is not None
    assert result.error.code == "unsupported_market"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_share_falls_back_from_tushare_to_akshare(monkeypatch):
    used: list[str] = []

    async def _tushare(**kwargs: Any) -> Result:
        used.append("tushare")
        return Result(
            success=False,
            error=Error(code="provider_unauthorized", message="bad token"),
        )

    async def _akshare(**kwargs: Any) -> Result:
        used.append("akshare")
        return Result(success=True, data=[BAR])

    monkeypatch.setattr("src.use_cases.ohlcv.fetch_tushare_ohlcv_result", _tushare)
    monkeypatch.setattr("src.use_cases.ohlcv.fetch_akshare_ohlcv_result", _akshare)

    service = build_ohlcv_service(_app_config(tushare={"token": "tushare-token"}))
    result = await service.fetch_bars(
        {"symbol": "000001.SZ", "market": "a_share", "interval": "1d"}
    )

    assert result.success is True
    assert used == ["tushare", "akshare"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_explicit_tushare_source_does_not_fall_back(monkeypatch):
    used: list[str] = []

    async def _tushare(**kwargs: Any) -> Result:
        used.append("tushare")
        return Result(
            success=False,
            error=Error(code="provider_unauthorized", message="bad token"),
        )

    async def _akshare(**kwargs: Any) -> Result:
        used.append("akshare")
        return Result(success=True, data=[BAR])

    monkeypatch.setattr("src.use_cases.ohlcv.fetch_tushare_ohlcv_result", _tushare)
    monkeypatch.setattr("src.use_cases.ohlcv.fetch_akshare_ohlcv_result", _akshare)

    service = build_ohlcv_service(_app_config(tushare={"token": "tushare-token"}))
    result = await service.fetch_bars(
        {
            "symbol": "000001.SZ",
            "market": "a_share",
            "interval": "1d",
            "source": "tushare",
        }
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "market_data_rejected"
    assert used == ["tushare"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_external_configuration_reaches_the_provider(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data=[BAR])

    monkeypatch.setattr("src.use_cases.ohlcv.fetch_crypto_ohlcv_result", _call)

    service = build_ohlcv_service(
        _app_config(binance={"apiKey": "key", "secret": "secret", "sandbox": True})
    )
    await service.fetch_bars(
        {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h"}
    )

    assert captured["venue"].api_key == "key"
    assert captured["venue"].secret == "secret"
    assert captured["venue"].sandbox is True
    assert captured["venue"].product == "spot"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_tushare_token_reaches_the_a_share_workflow(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data=[BAR])

    monkeypatch.setattr("src.use_cases.ohlcv.fetch_tushare_ohlcv_result", _call)

    service = build_ohlcv_service(_app_config(tushare={"token": "tushare-token"}))
    await service.fetch_bars(
        {"symbol": "000001.SZ", "market": "a_share", "interval": "1d"}
    )

    assert captured["token"] == "tushare-token"
