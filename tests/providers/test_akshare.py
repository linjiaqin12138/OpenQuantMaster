from unittest.mock import patch

import pandas as pd
import pytest

from src.providers.akshare import fetch_a_share_ohlcv, fetch_global_news, fetch_stock_news


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_a_share_ohlcv_normalizes_columns():
    frame = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2026-01-01"], utc=True),
            "开盘": [10.0],
            "最高": [11.0],
            "最低": [9.0],
            "收盘": [10.5],
            "成交量": [5000.0],
        }
    )

    with patch("akshare.stock_zh_a_hist", return_value=frame) as fetch:
        bars = await fetch_a_share_ohlcv(symbol="000001.SZ", interval="1d")

    assert fetch.call_args.kwargs["symbol"] == "000001"
    assert fetch.call_args.kwargs["period"] == "daily"
    assert bars[0]["close"] == 10.5
    assert bars[0]["timestamp"].startswith("2026-01-01")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_global_news_normalizes_each_source():
    frames = {
        "cls": pd.DataFrame(
            [
                {
                    "标题": "财联社标题",
                    "内容": "财联社正文",
                    "发布日期": "2026-01-02",
                    "发布时间": "03:04:05",
                }
            ]
        ),
        "sina": pd.DataFrame([{"时间": "2026-01-02 03:04:05", "内容": "新浪正文"}]),
    }

    with (
        patch("akshare.stock_info_global_cls", return_value=frames["cls"]),
        patch("akshare.stock_info_global_sina", return_value=frames["sina"]),
    ):
        cls_items = await fetch_global_news("cls")
        sina_items = await fetch_global_news("sina")

    assert cls_items[0]["title"] == "财联社标题"
    assert cls_items[0]["content"] == "财联社正文"
    assert cls_items[0]["published_at"] == "2026-01-01T19:04:05Z"
    assert sina_items[0]["source"] == "sina"
    assert sina_items[0]["content"] == "新浪正文"
    assert sina_items[0]["published_at"] == "2026-01-01T19:04:05Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_stock_news_normalizes_rows():
    frame = pd.DataFrame(
        [
            {
                "新闻标题": "公司公告",
                "新闻内容": "正文",
                "发布时间": "2026-01-02 03:04:05",
                "新闻链接": "https://stock",
            }
        ]
    )

    with patch("akshare.stock_news_em", return_value=frame) as fetch:
        items = await fetch_stock_news("603777")

    fetch.assert_called_once_with(symbol="603777")
    assert items[0]["symbol"] == "603777"
    assert items[0]["title"] == "公司公告"
    assert items[0]["url"] == "https://stock"
