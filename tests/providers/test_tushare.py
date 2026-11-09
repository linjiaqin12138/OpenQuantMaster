from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
import requests

from src.models.result import AppError
from src.providers.tushare import (
    fetch_a_share_ohlcv,
    fetch_a_share_ticker,
    fetch_a_share_ticker_result,
)


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


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_normalizes_the_snapshot_and_quote_time():
    fake_frame = pd.DataFrame(
        {
            "TS_CODE": ["600519.SH"],
            "NAME": ["贵州茅台"],
            "OPEN": [1440.0],
            "PRE_CLOSE": [1453.0],
            "PRICE": [1444.05],
            "HIGH": [1449.99],
            "LOW": [1435.08],
            "DATE": ["20261109"],
            "TIME": ["14:30:00"],
        }
    )

    with patch("tushare.realtime_quote", return_value=fake_frame) as realtime_quote:
        ticker = await fetch_a_share_ticker(token="token", symbol="600519.SH")

    realtime_quote.assert_called_once_with(ts_code="600519.SH", src="sina")
    assert ticker["name"] == "贵州茅台"
    assert ticker["price"] == 1444.05
    assert ticker["previous_close"] == 1453.0
    assert ticker["change"] == pytest.approx(-8.95)
    assert ticker["change_percent"] == pytest.approx(-8.95 / 1453.0 * 100)
    assert ticker["quote_time"] == "2026-11-09T06:30:00Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_an_empty_snapshot():
    with patch("tushare.realtime_quote", return_value=pd.DataFrame()):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="000300.SH")

    assert raised.value.code == "symbol_not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_a_missing_symbol():
    with patch("tushare.realtime_quote", return_value=None):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="000300.SZ")

    assert raised.value.code == "symbol_not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_a_symbol_without_a_usable_price():
    fake_frame = pd.DataFrame(
        {
            "TS_CODE": ["430047.BJ"],
            "NAME": ["诺思兰德"],
            "OPEN": [0.0],
            "PRE_CLOSE": [0.0],
            "PRICE": [0.0],
            "HIGH": [0.0],
            "LOW": [0.0],
            "DATE": ["20261109"],
            "TIME": ["15:00:00"],
        }
    )

    with patch("tushare.realtime_quote", return_value=fake_frame):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="430047.BJ")

    assert raised.value.code == "no_quote_data"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_result_maps_a_timeout():
    with patch(
        "tushare.realtime_quote",
        side_effect=requests.exceptions.Timeout("slow"),
    ):
        result = await fetch_a_share_ticker_result(token="token", symbol="510300.SH")

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_timeout"
