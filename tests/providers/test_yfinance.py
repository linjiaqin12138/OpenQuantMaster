from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.providers.yfinance import fetch_equity_ohlcv


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_equity_ohlcv_requests_the_ticker_and_parses_the_frame():
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

    with patch("yfinance.Ticker", return_value=fake_ticker) as ticker:
        bars = await fetch_equity_ohlcv(symbol="AAPL", interval="1d", limit=10)

    ticker.assert_called_once_with("AAPL")
    assert fake_ticker.history.call_args.kwargs["interval"] == "1d"
    assert bars[0]["close"] == 105.0
    assert bars[0]["timestamp"].startswith("2026-01-01")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_equity_ohlcv_forwards_the_requested_window():
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
        await fetch_equity_ohlcv(
            symbol="AAPL",
            interval="1d",
            start="2026-01-01",
            end="2026-02-01",
        )

    kwargs = fake_ticker.history.call_args.kwargs
    assert kwargs["start"] == "2026-01-01"
    assert kwargs["end"] == "2026-02-01"
