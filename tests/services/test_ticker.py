from typing import Any

import pytest

from src.composition import build_ticker_service
from src.config import AppConfig
from src.models.result import Error, Result

TICKER = {
    "name": "贵州茅台",
    "price": 1444.05,
    "previous_close": 1453.0,
    "open": 1440.0,
    "high": 1449.99,
    "low": 1435.08,
    "change": -8.95,
    "change_percent": -0.61610599,
    "quote_time": "2026-11-09T06:30:00Z",
}

CRYPTO_TICKER = {
    "name": "BTC/USDT:USDT",
    "price": 74326.1,
    "previous_close": None,
    "open": 75792.5,
    "high": 76000.0,
    "low": 74000.0,
    "change": -1466.4,
    "change_percent": -1.935,
    "bid": None,
    "ask": None,
    "quote_time": "2026-11-09T06:53:24.646Z",
}


def _app_config(token: str = "tushare-token", **providers: Any) -> AppConfig:
    sections: dict[str, Any] = {"tushare": {"token": token}}
    sections.update(providers)
    return AppConfig.model_validate({"providers": sections})


def _listing_provider(listed: dict[str, str], requested: list[str]):
    """Provider that only knows the given ``symbol`` -> ``name`` listings."""

    async def _call(**kwargs: Any) -> Result:
        symbol = kwargs["symbol"]
        requested.append(symbol)
        if symbol not in listed:
            return Result(
                success=False,
                error=Error(code="symbol_not_found", message="no ticker"),
            )
        return Result(success=True, data={**TICKER, "name": listed[symbol]})

    return _call


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_returns_a_timestamped_snapshot(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data=TICKER)

    monkeypatch.setattr("src.use_cases.ticker.fetch_a_share_ticker_result", _call)
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker({"symbol": "600519.SH", "market": "a_share"})

    assert result.success is True
    assert captured == {"token": "tushare-token", "symbol": "600519.SH"}
    assert result.data["symbol"] == "600519.SH"
    assert result.data["source"] == "tushare"
    assert result.data["price"] == 1444.05
    assert result.data["quote_time"] == "2026-11-09T06:30:00Z"
    assert result.data["fetched_at"].endswith("Z")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_derives_the_exchange_suffix(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        "src.use_cases.ticker.fetch_a_share_ticker_result",
        _listing_provider({"515070.SH": "人工智能ETF华夏"}, requested),
    )
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker({"symbol": "515070", "market": "a_share"})

    assert result.success is True
    assert requested == ["515070.SH", "515070.SZ"]
    assert result.data["symbol"] == "515070.SH"
    assert result.data["name"] == "人工智能ETF华夏"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_falls_back_to_the_other_exchange(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        "src.use_cases.ticker.fetch_a_share_ticker_result",
        _listing_provider({"000300.SH": "沪深300"}, requested),
    )
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker({"symbol": "000300", "market": "a_share"})

    assert result.success is True
    assert requested == ["000300.SZ", "000300.SH"]
    assert result.data["symbol"] == "000300.SH"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_rejects_a_code_listed_on_two_exchanges(monkeypatch):
    requested: list[str] = []
    monkeypatch.setattr(
        "src.use_cases.ticker.fetch_a_share_ticker_result",
        _listing_provider(
            {"000001.SH": "上证指数", "000001.SZ": "平安银行"},
            requested,
        ),
    )
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker({"symbol": "000001", "market": "a_share"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "ambiguous_symbol"
    assert "000001.SH" in result.error.message
    assert "000001.SZ" in result.error.message
    assert requested == ["000001.SZ", "000001.SH"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_reads_a_crypto_snapshot_from_the_configured_venue(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data=CRYPTO_TICKER)

    monkeypatch.setattr("src.use_cases.ticker.fetch_crypto_ticker_result", _call)
    service = build_ticker_service(
        _app_config(
            binance={"exchange": "binance", "product": "usdm", "sandbox": True},
        )
    )

    result = await service.fetch_ticker(
        {"symbol": "BTC/USDT:USDT", "market": "crypto"}
    )

    assert result.success is True
    venue = captured["venue"]
    assert venue.exchange == "binance"
    assert venue.product == "usdm"
    assert venue.sandbox is True
    assert captured["symbol"] == "BTC/USDT:USDT"
    assert result.data["source"] == "ccxt"
    assert result.data["price"] == 74326.1
    assert result.data["previous_close"] is None
    assert result.data["quote_time"] == "2026-11-09T06:53:24.646Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_reads_a_perpetual_symbol_from_the_usdm_venue(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data=CRYPTO_TICKER)

    monkeypatch.setattr("src.use_cases.ticker.fetch_crypto_ticker_result", _call)
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker(
        {"symbol": "BTC/USDT:USDT", "market": "crypto"}
    )

    assert result.success is True
    assert captured["venue"].product == "usdm"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_requires_a_tushare_token():
    service = build_ticker_service(_app_config(token=""))

    result = await service.fetch_ticker({"symbol": "600519.SH", "market": "a_share"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "missing_provider_token"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_rejects_a_symbol_that_is_not_an_a_share_code():
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker({"symbol": "AAPL", "market": "a_share"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_input"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_ticker_maps_a_provider_outage(monkeypatch):
    async def _call(**kwargs: Any) -> Result:
        return Result(
            success=False,
            error=Error(code="provider_unavailable", message="provider failed"),
        )

    monkeypatch.setattr("src.use_cases.ticker.fetch_a_share_ticker_result", _call)
    service = build_ticker_service(_app_config())

    result = await service.fetch_ticker({"symbol": "600519.SH", "market": "a_share"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "market_data_unavailable"
