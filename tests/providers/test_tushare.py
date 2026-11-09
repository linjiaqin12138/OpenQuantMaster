from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from src.providers.tushare import fetch_a_share_ohlcv


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ohlcv_uses_the_token_and_parses_the_frame():
    fake_frame = pd.DataFrame(
        {
            "trade_date": ["20260102"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "vol": [5000.0],
        }
    )
    fake_pro = MagicMock()
    fake_pro.daily.return_value = fake_frame

    with patch("tushare.pro_api", return_value=fake_pro) as pro_api:
        bars = await fetch_a_share_ohlcv(token="token", symbol="000001.SZ")

    pro_api.assert_called_once_with("token")
    assert fake_pro.daily.call_args.kwargs["ts_code"] == "000001.SZ"
    assert bars[0]["close"] == 10.5
    assert bars[0]["timestamp"].startswith("2026-01-02")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ohlcv_forwards_the_requested_window():
    fake_frame = pd.DataFrame(
        {
            "trade_date": ["20260102"],
            "open": [10.0],
            "high": [11.0],
            "low": [9.0],
            "close": [10.5],
            "vol": [5000.0],
        }
    )
    fake_pro = MagicMock()
    fake_pro.daily.return_value = fake_frame

    with patch("tushare.pro_api", return_value=fake_pro):
        await fetch_a_share_ohlcv(
            token="token",
            symbol="000001.SZ",
            start="2026-01-01",
            end="2026-02-01",
        )

    kwargs = fake_pro.daily.call_args.kwargs
    assert kwargs["start_date"] == "20260101"
    assert kwargs["end_date"] == "20260201"
