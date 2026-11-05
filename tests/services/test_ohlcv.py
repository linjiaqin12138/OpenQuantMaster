from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from src.config import AppConfig
from src.services.ohlcv import OHLCV, OHLCVConfig, OHLCVCryptoConfig


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_fetches_crypto_ccxt():
    class FakeExchange:
        def __init__(self, *args, **kwargs) -> None:
            self.fetch_ohlcv = AsyncMock(
                return_value=[
                    [1_000_000_000_000, 100.0, 110.0, 90.0, 105.0, 1000.0],
                ]
            )
            self.close = AsyncMock()
            self.set_sandbox_mode = MagicMock()

    fake_ccxt_module = type("ccxt", (), {"binance": FakeExchange})()
    cfg = OHLCVConfig(
        crypto=OHLCVCryptoConfig(exchange="binance", product="spot", sandbox=False)
    )

    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt_module}):
        result = await OHLCV(cfg).run(
            {
                "symbol": "BTCUSDT",
                "market": "crypto",
                "interval": "1h",
                "limit": 1,
            }
        )

    assert result.success is True
    assert result.data["symbol"] == "BTCUSDT"
    assert result.data["rows"] == 1
    assert len(result.data["bars"]) == 1
    assert result.data["bars"][0]["open"] == 100.0
    assert result.data["bars"][0]["close"] == 105.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_rejects_invalid_market():
    result = await OHLCV(OHLCVConfig()).run(
        {"symbol": "BTCUSDT", "market": "forex", "interval": "1h"}
    )
    assert result.success is False
    assert result.error is not None
    assert "market" in result.error.message.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_fetches_us_equity_yfinance():
    fake_hist = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2026-01-01"], utc=True),
            "Open": [100.0],
            "High": [110.0],
            "Low": [90.0],
            "Close": [105.0],
            "Volume": [1000.0],
        }
    )

    fake_ticker = MagicMock()
    fake_ticker.history.return_value = fake_hist

    with patch("yfinance.Ticker", return_value=fake_ticker):
        result = await OHLCV(OHLCVConfig()).run(
            {"symbol": "AAPL", "market": "us_equity", "interval": "1d"}
        )

    assert result.success is True
    assert result.data["market"] == "us_equity"
    assert result.data["rows"] == 1
    assert result.data["bars"][0]["close"] == 105.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_fetches_a_share_akshare_fallback():
    fake_df = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2026-01-01"], utc=True),
            "开盘": [10.0],
            "最高": [11.0],
            "最低": [9.0],
            "收盘": [10.5],
            "成交量": [5000.0],
        }
    )

    with patch("akshare.stock_zh_a_hist", return_value=fake_df):
        result = await OHLCV(OHLCVConfig(tushare_token="bad-token")).run(
            {"symbol": "000001.SZ", "market": "a_share", "interval": "1d"}
        )

    assert result.success is True
    assert result.data["market"] == "a_share"
    assert result.data["rows"] == 1
    assert result.data["bars"][0]["close"] == 10.5


def test_ohlcv_config_from_app_config_extracts_provider_settings():
    app_config = AppConfig.model_validate(
        {
            "providers": {
                "binance": {"apiKey": "key", "secret": "secret"},
                "tushare": {"token": "token"},
            }
        }
    )

    config = OHLCVConfig.from_config(app_config)

    assert config.crypto.exchange == "binance"
    assert config.crypto.product == "spot"
    assert config.crypto.sandbox is False
    assert config.crypto.api_key == "key"
    assert config.crypto.secret == "secret"
    assert config.tushare_token == "token"
