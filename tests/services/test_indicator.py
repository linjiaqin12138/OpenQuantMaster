from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.composition import build_indicator_service
from src.config import AppConfig
from src.models.result import Error, Result


def _bars(count: int = 50) -> list[dict]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    bars = [
        {
            "timestamp": (start + timedelta(hours=index)).isoformat(),
            "open": 100.0 + index,
            "high": 102.0 + index,
            "low": 99.0 + index,
            "close": 101.0 + index,
            "volume": 1000.0,
        }
        for index in range(count)
    ]
    # Rows crafted to produce a doji pattern.
    if count > 10:
        bars[10] = {**bars[10], "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0}
    return bars


def _provider(count: int = 50):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=True, data=_bars(count))

    return _call


def _app_config() -> AppConfig:
    return AppConfig.model_validate({"providers": {}})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compute_returns_indicators_for_given_bars():
    service = build_indicator_service(_app_config())

    result = await service.compute(
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "bars": _bars(),
            "indicators": ["sma", "rsi"],
            "patterns": ["DOJI"],
        }
    )

    assert result.success is True
    assert result.data["symbol"] == "BTCUSDT"
    assert result.data["rows"] == 50
    assert result.data["indicators"]["sma"]["value"] is not None
    assert 0 <= result.data["indicators"]["rsi"]["value"] <= 100
    assert result.data["patterns"]["history"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compute_fetches_the_bars_of_a_symbol(monkeypatch):
    monkeypatch.setattr("src.use_cases.ohlcv.fetch_crypto_ohlcv_result", _provider())

    service = build_indicator_service(_app_config())
    result = await service.compute(
        {
            "symbol": "BTCUSDT",
            "market": "crypto",
            "interval": "1h",
            "limit": 50,
            "indicators": ["rsi"],
        }
    )

    assert result.success is True
    assert result.data["rows"] == 50
    assert result.data["indicators"]["rsi"]["value"] is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compute_reports_a_market_data_failure(monkeypatch):
    async def _call(**kwargs: Any) -> Result:
        return Result(
            success=False,
            error=Error(code="provider_unavailable", message="down"),
        )

    monkeypatch.setattr("src.use_cases.ohlcv.fetch_crypto_ohlcv_result", _call)

    service = build_indicator_service(_app_config())
    result = await service.compute(
        {
            "symbol": "BTCUSDT",
            "market": "crypto",
            "interval": "1h",
            "indicators": ["rsi"],
        }
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "market_data_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compute_rejects_a_request_without_bars_or_symbol():
    service = build_indicator_service(_app_config())

    result = await service.compute({"indicators": ["rsi"]})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert "bars" in result.error.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compute_rejects_an_unknown_indicator():
    service = build_indicator_service(_app_config())

    result = await service.compute(
        {
            "symbol": "BTCUSDT",
            "bars": _bars(),
            "indicators": ["NOT_AN_INDICATOR"],
        }
    )

    assert result.error is not None
    assert result.error.code == "unknown_indicator"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_compute_rejects_insufficient_data():
    service = build_indicator_service(_app_config())

    result = await service.compute(
        {
            "symbol": "BTCUSDT",
            "bars": _bars(count=3),
            "indicators": ["sma", "macd"],
            "patterns": ["DOJI"],
        }
    )

    assert result.error is not None
    assert result.error.code == "insufficient_data"
