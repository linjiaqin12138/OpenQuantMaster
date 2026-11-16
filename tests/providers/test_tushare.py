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


def _pro(frame: pd.DataFrame, *, name: str = "贵州茅台") -> MagicMock:
    fake_pro = MagicMock()
    fake_pro.daily.return_value = frame
    fake_pro.index_daily.return_value = frame
    fake_pro.fund_daily.return_value = frame
    fake_pro.stock_basic.return_value = pd.DataFrame({"ts_code": ["600519.SH"], "name": [name]})
    fake_pro.index_basic.return_value = pd.DataFrame({"ts_code": ["000001.SH"], "name": [name]})
    fake_pro.fund_basic.return_value = pd.DataFrame({"ts_code": ["515070.SH"], "name": [name]})
    return fake_pro


def _daily_frame(**overrides: object) -> pd.DataFrame:
    row = {
        "ts_code": "600519.SH",
        "trade_date": "20261109",
        "open": 1440.0,
        "high": 1449.99,
        "low": 1435.08,
        "close": 1444.05,
        "pre_close": 1453.0,
    }
    row.update(overrides)
    return pd.DataFrame({key: [value] for key, value in row.items()})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reads_the_latest_pro_daily_bar():
    fake_pro = _pro(_daily_frame())

    with patch("tushare.pro_api", return_value=fake_pro) as pro_api:
        ticker = await fetch_a_share_ticker(token="token", symbol="600519.SH")

    pro_api.assert_called_once_with("token")
    assert fake_pro.daily.call_args.kwargs["ts_code"] == "600519.SH"
    assert len(fake_pro.daily.call_args.kwargs["start_date"]) == 8
    fake_pro.index_daily.assert_not_called()
    assert fake_pro.stock_basic.call_args.kwargs["ts_code"] == "600519.SH"
    assert ticker["name"] == "贵州茅台"
    assert ticker["price"] == 1444.05
    assert ticker["previous_close"] == 1453.0
    assert ticker["change"] == pytest.approx(-8.95)
    assert ticker["change_percent"] == pytest.approx(-8.95 / 1453.0 * 100)
    assert ticker["quote_time"] == "2026-11-09T07:00:00Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_keeps_the_newest_daily_bar():
    fake_pro = _pro(
        pd.DataFrame(
            {
                "ts_code": ["600519.SH", "600519.SH"],
                "trade_date": ["20261106", "20261109"],
                "open": [1.0, 1440.0],
                "high": [1.0, 1449.99],
                "low": [1.0, 1435.08],
                "close": [1.0, 1444.05],
                "pre_close": [1.0, 1453.0],
            }
        )
    )

    with patch("tushare.pro_api", return_value=fake_pro):
        ticker = await fetch_a_share_ticker(token="token", symbol="600519.SH")

    assert ticker["price"] == 1444.05
    assert ticker["quote_time"] == "2026-11-09T07:00:00Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reads_an_index_from_index_daily():
    fake_pro = _pro(_daily_frame(ts_code="000001.SH", close=3634.353), name="上证指数")

    with patch("tushare.pro_api", return_value=fake_pro):
        ticker = await fetch_a_share_ticker(token="token", symbol="000001.SH")

    fake_pro.daily.assert_not_called()
    assert fake_pro.index_daily.call_args.kwargs["ts_code"] == "000001.SH"
    assert ticker["name"] == "上证指数"
    assert ticker["price"] == 3634.353


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_an_empty_snapshot():
    with patch("tushare.pro_api", return_value=_pro(pd.DataFrame())):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="600519.SZ")

    assert raised.value.code == "symbol_not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_a_missing_symbol():
    with patch("tushare.pro_api", return_value=_pro(pd.DataFrame())):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="000300.SZ")

    assert raised.value.code == "symbol_not_found"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_a_symbol_without_a_usable_price():
    with patch("tushare.pro_api", return_value=_pro(_daily_frame(ts_code="430047.BJ", close=0.0))):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="430047.BJ")

    assert raised.value.code == "no_quote_data"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_reports_a_missing_fund_permission():
    fake_pro = _pro(pd.DataFrame())
    fake_pro.fund_daily.side_effect = Exception("抱歉，您没有接口(fund_daily)访问权限")

    with patch("tushare.pro_api", return_value=fake_pro):
        with pytest.raises(AppError) as raised:
            await fetch_a_share_ticker(token="token", symbol="515070.SH")

    assert raised.value.code == "provider_unauthorized"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ticker_result_maps_a_timeout():
    fake_pro = _pro(pd.DataFrame())
    fake_pro.daily.side_effect = requests.exceptions.Timeout("slow")

    with patch("tushare.pro_api", return_value=fake_pro):
        result = await fetch_a_share_ticker_result(token="token", symbol="600519.SH")

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_timeout"
