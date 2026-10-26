from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from tools.market_data.ohlcv_tool import OHLCVTool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_tool_fetches_crypto_ccxt(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: ./artifacts
  logs: ./logs
  database: ./data/runtime.db
scheduler:
  timezone: UTC
event_bus:
  backend: memory
logging:
  level: INFO
  format: json
exchanges:
  binance:
    apiKey: ""
    secret: ""
    spot:
      ccxt_id: binance
      sandbox: false
market_data:
  crypto:
    exchange: binance
    product: spot
"""
    )

    class FakeExchange:
        def __init__(self, *args, **kwargs) -> None:
            self.fetch_ohlcv = AsyncMock(
                return_value=[
                    [1_000_000_000_000, 100.0, 110.0, 90.0, 105.0, 1000.0],
                ]
            )
            self.close = AsyncMock()
            self.set_sandbox_mode = AsyncMock()

    fake_ccxt_module = type("ccxt", (), {"binance": FakeExchange})()

    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt_module}):
        tool = OHLCVTool()
        result = await tool.execute(
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
    assert len(result.artifacts) == 1
    assert "timestamp,open,high,low,close,volume" in result.artifacts[0].content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_tool_rejects_invalid_market(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("app_name: OpenQuantMaster\nenvironment: testing\n")
    tool = OHLCVTool()
    result = await tool.execute(
        {"symbol": "BTCUSDT", "market": "forex", "interval": "1h"}
    )
    assert result.success is False
    assert "market" in result.error.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_tool_fetches_us_equity_yfinance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("app_name: OpenQuantMaster\nenvironment: testing\n")

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
        tool = OHLCVTool()
        result = await tool.execute(
            {"symbol": "AAPL", "market": "us_equity", "interval": "1d"}
        )

    assert result.success is True
    assert result.data["market"] == "us_equity"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_ohlcv_tool_fetches_a_share_akshare_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
app_name: OpenQuantMaster
environment: testing
market_data:
  equities:
    tushare_token: bad-token
"""
    )

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
        tool = OHLCVTool()
        result = await tool.execute(
            {"symbol": "000001.SZ", "market": "a_share", "interval": "1d"}
        )

    assert result.success is True
    assert result.data["market"] == "a_share"
