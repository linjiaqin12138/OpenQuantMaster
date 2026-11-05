from unittest.mock import patch

import pandas as pd
import pytest

from src.services.news_fetcher import NewsFetcher


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_recent_normalizes_all_sources():
    frames = {
        "stock_info_global_cls": pd.DataFrame(
            [{"标题": "财联社标题", "内容": "财联社正文", "发布日期": "2026-01-02", "发布时间": "03:04:05"}]
        ),
        "stock_info_global_em": pd.DataFrame(
            [{"标题": "东财标题", "摘要": "东财摘要", "发布时间": "2026-01-02 03:04:05", "链接": "https://em"}]
        ),
        "stock_info_global_sina": pd.DataFrame(
            [{"时间": "2026-01-02 03:04:05", "内容": "新浪正文"}]
        ),
        "stock_info_global_ths": pd.DataFrame(
            [{"标题": "同花顺标题", "内容": "同花顺正文", "发布时间": "2026-01-02 03:04:05", "链接": "https://ths"}]
        ),
        "stock_info_global_futu": pd.DataFrame(
            [{"标题": "富途标题", "内容": "富途正文", "发布时间": "2026-01-02 03:04:05", "链接": "https://futu"}]
        ),
    }
    patches = [patch(f"akshare.{name}", return_value=frame) for name, frame in frames.items()]
    for patcher in patches:
        patcher.start()
    try:
        result = await NewsFetcher().run({"mode": "recent"})
    finally:
        for patcher in patches:
            patcher.stop()

    assert result.success is True
    assert result.data["rows"] == 5
    assert {item["source"] for item in result.data["items"]} == {"cls", "em", "sina", "ths", "futu"}
    assert all(item["published_at"] == "2026-01-01T19:04:05Z" for item in result.data["items"])
    assert result.data["coverage"] == {
        "earliest": "2026-01-01T19:04:05Z",
        "latest": "2026-01-01T19:04:05Z",
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_stock_recent_uses_eastmoney_symbol():
    frame = pd.DataFrame(
        [
            {
                "关键词": "603777",
                "新闻标题": "公司公告",
                "新闻内容": "正文",
                "发布时间": "2026-01-02 03:04:05",
                "文章来源": "东方财富",
                "新闻链接": "https://stock",
            }
        ]
    )
    with patch("akshare.stock_news_em", return_value=frame) as fetch:
        result = await NewsFetcher().run({"mode": "stock_recent", "symbol": "603777"})

    fetch.assert_called_once_with(symbol="603777")
    assert result.success is True
    assert result.data["rows"] == 1
    assert result.data["items"][0]["symbol"] == "603777"
    assert result.data["items"][0]["url"] == "https://stock"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_keywords_filter_any_and_all():
    frame = pd.DataFrame(
        [
            {"时间": "2026-01-02 03:04:05", "内容": "央行宣布降息"},
            {"时间": "2026-01-02 03:05:05", "内容": "央行开展逆回购"},
            {"时间": "2026-01-02 03:06:05", "内容": "指数上涨"},
        ]
    )
    with patch("akshare.stock_info_global_sina", return_value=frame):
        any_result = await NewsFetcher().run(
            {"sources": ["sina"], "keywords": ["降息", "逆回购"], "keyword_match": "any"}
        )
        all_result = await NewsFetcher().run(
            {"sources": ["sina"], "keywords": ["央行", "降息"], "keyword_match": "all"}
        )

    assert any_result.data["rows"] == 2
    assert any_result.data["source_stats"]["sina"]["filtered"] == 1
    assert all_result.data["rows"] == 1
    assert all_result.data["items"][0]["content"] == "央行宣布降息"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_deduplicates_sorts_and_applies_global_limit():
    cls_frame = pd.DataFrame(
        [
            {"标题": "相同", "内容": "正文", "发布日期": "2026-01-02", "发布时间": "03:04:05"},
            {"标题": "较早", "内容": "旧闻", "发布日期": "2026-01-01", "发布时间": "03:04:05"},
        ]
    )
    ths_frame = pd.DataFrame(
        [{"标题": "相同", "内容": "正文", "发布时间": "2026-01-02 03:04:05", "链接": "https://ths"}]
    )
    with (
        patch("akshare.stock_info_global_cls", return_value=cls_frame),
        patch("akshare.stock_info_global_ths", return_value=ths_frame),
    ):
        result = await NewsFetcher().run({"sources": ["cls", "ths"], "limit": 1})

    assert result.success is True
    assert result.data["rows"] == 1
    assert result.data["items"][0]["title"] == "相同"
    assert result.data["source_stats"]["cls"]["duplicates"] == 1
    assert result.data["source_stats"]["ths"]["returned"] == 1
    assert sum(stat["returned"] for stat in result.data["source_stats"].values()) == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_partial_source_failure():
    frame = pd.DataFrame([{"时间": "2026-01-02 03:04:05", "内容": "新浪正文"}])
    with (
        patch("akshare.stock_info_global_cls", side_effect=RuntimeError("cls unavailable")),
        patch("akshare.stock_info_global_sina", return_value=frame),
    ):
        result = await NewsFetcher().run({"sources": ["cls", "sina"]})

    assert result.success is True
    assert result.data["rows"] == 1
    assert result.data["errors"][0]["source"] == "cls"
    assert result.data["errors"][0]["code"] == "source_fetch_failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_all_sources_failed():
    with patch("akshare.stock_info_global_cls", side_effect=RuntimeError("unavailable")):
        result = await NewsFetcher().run({"sources": ["cls"]})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "all_sources_failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_empty_filtered_result_is_success():
    frame = pd.DataFrame([{"时间": "2026-01-02 03:04:05", "内容": "指数上涨"}])
    with patch("akshare.stock_info_global_sina", return_value=frame):
        result = await NewsFetcher().run({"sources": ["sina"], "keywords": ["降息"]})

    assert result.success is True
    assert result.data["rows"] == 0
    assert result.data["coverage"] == {"earliest": None, "latest": None}


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "inputs, expected_field",
    [
        ({"mode": "stock_recent"}, "symbol"),
        ({"mode": "stock_recent", "symbol": "603777", "sources": ["em"]}, "sources"),
        ({"mode": "recent", "symbol": "603777"}, "symbol"),
        ({"mode": "recent", "sources": ["unknown"]}, "sources"),
    ],
)
async def test_news_rejects_invalid_mode_params(inputs, expected_field):
    result = await NewsFetcher().run(inputs)

    assert result.success is False
    assert result.error is not None
    assert expected_field in result.error.message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_rejects_invalid_source_timestamp():
    frame = pd.DataFrame([{"时间": "not-a-time", "内容": "新浪正文"}])
    with patch("akshare.stock_info_global_sina", return_value=frame):
        result = await NewsFetcher().run({"sources": ["sina"]})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "all_sources_failed"
