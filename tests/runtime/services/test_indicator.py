from unittest.mock import AsyncMock, patch

import numpy as np
import pandas as pd
import pytest
import talib

from runtime.services.indicator import Indicator
from runtime.services.ohlcv import OHLCV, OHLCVConfig, OHLCVCryptoConfig


def _make_bars(n: int = 50) -> list[dict]:
    np.random.seed(42)
    base = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "open": base,
            "high": base + np.abs(np.random.randn(n)) * 1.5,
            "low": base - np.abs(np.random.randn(n)) * 1.5,
            "close": base + np.random.randn(n) * 1.0,
            "volume": np.random.randint(1000, 10000, n),
        }
    )
    df.loc[10, ["open", "high", "low", "close"]] = [100.0, 100.5, 99.5, 100.0]
    df.loc[29, ["open", "high", "low", "close"]] = [102.0, 102.2, 100.5, 100.8]
    df.loc[30, ["open", "high", "low", "close"]] = [100.0, 103.0, 99.5, 102.5]
    out = df.copy()
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S%z")
    return out.to_dict(orient="records")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_from_bars():
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "interval": "1h",
            "bars": _make_bars(),
            "indicators": ["sma", "ema", "macd", "rsi", "boll", "atr"],
            "patterns": ["DOJI", "ENGULFING"],
        }
    )

    assert result.success is True
    data = result.data
    assert data["symbol"] == "BTCUSDT"
    assert data["interval"] == "1h"
    assert data["rows"] == 50

    indicators = data["indicators"]
    assert "sma" in indicators
    assert "rsi" in indicators
    assert 0 <= indicators["rsi"]["value"] <= 100
    assert indicators["sma"]["value"] > 0
    assert indicators["sma"]["params"]["timeperiod"] == 30
    assert indicators["boll"]["upperband"] >= indicators["boll"]["middleband"]
    assert indicators["boll"]["middleband"] >= indicators["boll"]["lowerband"]
    assert indicators["macd"]["params"]["fastperiod"] == 12

    patterns = data["patterns"]
    assert patterns["last_bullish"] is not None or patterns["last_bearish"] is not None
    assert any(entry["pattern"] == "DOJI" for entry in patterns["history"])
    assert "BTCUSDT" in data["summary"]
    assert "1h" in data["summary"]


def _ccxt_ohlcv_rows(n: int = 50) -> list[list[float]]:
    np.random.seed(42)
    base = 100 + np.cumsum(np.random.randn(n) * 0.5)
    start_ms = 1_700_000_000_000
    rows: list[list[float]] = []
    for i in range(n):
        o = float(base[i])
        h = o + abs(float(np.random.randn())) * 1.5
        low = o - abs(float(np.random.randn())) * 1.5
        c = o + float(np.random.randn())
        v = float(np.random.randint(1000, 10000))
        rows.append([start_ms + i * 3_600_000, o, h, low, c, v])
    return rows


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_from_symbol_via_ohlcv():
    class FakeExchange:
        def __init__(self, *args, **kwargs) -> None:
            self.fetch_ohlcv = AsyncMock(return_value=_ccxt_ohlcv_rows(50))
            self.close = AsyncMock()
            self.set_sandbox_mode = AsyncMock()

    fake_ccxt_module = type("ccxt", (), {"binance": FakeExchange})()
    ohlcv = OHLCV(
        OHLCVConfig(crypto=OHLCVCryptoConfig(exchange="binance", product="spot"))
    )

    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt_module}):
        result = await Indicator(ohlcv=ohlcv).run(
            {
                "symbol": "BTC/USDT",
                "market": "crypto",
                "interval": "1h",
                "limit": 50,
            }
        )

    assert result.success is True
    assert result.data["symbol"] == "BTC/USDT"
    assert result.data["rows"] == 50
    assert result.data["indicators"]["rsi"]["value"] is not None
    assert result.data["patterns"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_rejects_insufficient_data():
    small_bars = _make_bars(n=3)
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": small_bars,
            "indicators": ["sma", "macd"],
            "patterns": ["DOJI"],
        }
    )
    assert result.success is False
    assert "Insufficient data" in (result.error or "")
    assert "33" in (result.error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_rejects_missing_bars_without_ohlcv():
    result = await Indicator().run({"indicators": ["rsi"]})
    assert result.success is False
    assert "bars" in (result.error or "").lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_rejects_symbol_without_ohlcv():
    result = await Indicator().run(
        {"symbol": "BTCUSDT", "market": "crypto", "indicators": ["rsi"]}
    )
    assert result.success is False
    assert "bars" in (result.error or "").lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_dynamic_indicators():
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": _make_bars(),
            "indicators": ["ADX", "OBV", "STOCH"],
        }
    )
    assert result.success is True
    indicators = result.data["indicators"]
    assert indicators["ADX"]["value"] is not None
    assert indicators["OBV"]["value"] is not None
    assert indicators["STOCH"]["slowk"] is not None
    assert indicators["STOCH"]["slowd"] is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_params():
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": _make_bars(),
            "indicators": ["sma", "macd"],
            "indicator_params": {
                "SMA": {"timeperiod": 10},
                "MACD": {"fastperiod": 5, "slowperiod": 15, "signalperiod": 3},
            },
        }
    )
    assert result.success is True
    assert result.data["indicators"]["sma"]["params"]["timeperiod"] == 10
    macd = result.data["indicators"]["macd"]
    assert macd["params"]["fastperiod"] == 5
    assert macd["params"]["slowperiod"] == 15
    assert macd["params"]["signalperiod"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_patterns_default_none():
    result = await Indicator().run(
        {"symbol": "BTCUSDT", "bars": _make_bars(), "indicators": ["rsi"]}
    )
    assert result.success is True
    assert result.data["patterns"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_patterns_bare_names():
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": _make_bars(),
            "indicators": ["rsi"],
            "patterns": ["ENGULFING", "DOJI", "HAMMER"],
        }
    )
    assert result.success is True
    patterns = result.data["patterns"]
    assert isinstance(patterns["history"], list)
    if patterns["history"]:
        entry = patterns["history"][0]
        assert entry["label"] in ("bullish", "bearish", "neutral")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_patterns_all_61():
    all_patterns = [name[3:] for name in talib.get_functions() if name.startswith("CDL")]
    assert len(all_patterns) == 61

    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": _make_bars(),
            "indicators": ["SMA"],
            "patterns": all_patterns,
        }
    )
    assert result.success is True
    patterns = result.data["patterns"]
    assert isinstance(patterns["history"], list)
    if patterns["history"]:
        assert patterns["last_bullish"] is not None or patterns["last_bearish"] is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_rejects_unknown_indicator():
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": _make_bars(),
            "indicators": ["NOT_AN_INDICATOR"],
        }
    )
    assert result.success is False
    assert "Unknown indicator function" in (result.error or "")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_runtime_failed_indicator():
    result = await Indicator().run(
        {
            "symbol": "BTCUSDT",
            "bars": _make_bars(),
            "indicators": ["MAVP"],
        }
    )
    assert result.success is True
    assert "error" in result.data["indicators"]["MAVP"]
