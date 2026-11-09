from __future__ import annotations

import asyncio
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.models.result import as_call_result
from src.providers.base import map_requests_error
from src.utils.time import format_utc_iso, parse_iso_to_utc

_CHINA_TZ = ZoneInfo("Asia/Shanghai")

_GLOBAL_NEWS_FUNCTIONS = {
    "cls": "stock_info_global_cls",
    "em": "stock_info_global_em",
    "sina": "stock_info_global_sina",
    "ths": "stock_info_global_ths",
    "futu": "stock_info_global_futu",
}

_A_SHARE_PERIODS = {
    "1d": "daily",
    "d": "daily",
    "D": "daily",
    "1w": "weekly",
    "w": "weekly",
    "W": "weekly",
    "1M": "monthly",
    "m": "monthly",
    "M": "monthly",
    "monthly": "monthly",
}

_A_SHARE_COLUMNS = {
    "日期": "timestamp",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
}


async def fetch_a_share_ohlcv(
    *,
    symbol: str,
    interval: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch daily bars for an A-share code through AkShare."""
    return await asyncio.to_thread(
        _fetch_a_share_ohlcv_sync,
        symbol=symbol,
        interval=interval,
        start=start,
        end=end,
    )


def _fetch_a_share_ohlcv_sync(
    *,
    symbol: str,
    interval: str,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    import akshare as ak

    # Strip exchange suffix, e.g. 000001.SZ -> 000001
    code = symbol.split(".")[0]
    start_date = (start or "")[:10].replace("-", "") or "19700101"
    end_date = (end or "")[:10].replace("-", "") or "20991231"
    df = ak.stock_zh_a_hist(
        symbol=code,
        period=_A_SHARE_PERIODS.get(interval, "daily"),
        start_date=start_date,
        end_date=end_date,
        adjust="",
    )
    df = df.rename(columns=_A_SHARE_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    bars = df.to_dict(orient="records")
    for bar in bars:
        bar["timestamp"] = pd.Timestamp(bar["timestamp"]).isoformat()
    return bars


async def fetch_global_news(source: str) -> list[dict[str, Any]]:
    """Fetch the latest flash news of one AkShare global source."""
    return await asyncio.to_thread(_fetch_global_news_sync, source)


def _fetch_global_news_sync(source: str) -> list[dict[str, Any]]:
    import akshare as ak

    function_name = _GLOBAL_NEWS_FUNCTIONS.get(source)
    if function_name is None:
        raise ValueError(f"Unsupported news source: {source}")
    df = getattr(ak, function_name)()
    return [_normalize_global_row(source, row) for row in df.to_dict(orient="records")]


async def fetch_stock_news(symbol: str) -> list[dict[str, Any]]:
    """Fetch the latest Eastmoney news of one stock code."""
    return await asyncio.to_thread(_fetch_stock_news_sync, symbol)


def _fetch_stock_news_sync(symbol: str) -> list[dict[str, Any]]:
    import akshare as ak

    df = ak.stock_news_em(symbol=symbol)
    return [_normalize_stock_row(symbol, row) for row in df.to_dict(orient="records")]


def _normalize_global_row(source: str, row: dict[str, Any]) -> dict[str, Any]:
    if source == "cls":
        published = f"{_text(row.get('发布日期'))} {_text(row.get('发布时间'))}"
        title = _text(row.get("标题"))
        summary = None
        content = _text(row.get("内容"))
        url = None
    elif source == "em":
        published = _text(row.get("发布时间"))
        title = _text(row.get("标题"))
        summary = _optional_text(row.get("摘要"))
        content = None
        url = _optional_text(row.get("链接"))
    elif source == "sina":
        published = _text(row.get("时间"))
        title = ""
        summary = None
        content = _text(row.get("内容"))
        url = None
    else:
        published = _text(row.get("发布时间"))
        title = _text(row.get("标题"))
        summary = None
        content = _optional_text(row.get("内容"))
        url = _optional_text(row.get("链接"))
    return _news_item(source, None, title, summary, content, url, published)


def _normalize_stock_row(symbol: str, row: dict[str, Any]) -> dict[str, Any]:
    return _news_item(
        "em",
        symbol,
        _text(row.get("新闻标题")),
        None,
        _optional_text(row.get("新闻内容")),
        _optional_text(row.get("新闻链接")),
        _text(row.get("发布时间")),
    )


def _news_item(
    source: str,
    symbol: str | None,
    title: str,
    summary: str | None,
    content: str | None,
    url: str | None,
    published: str,
) -> dict[str, Any]:
    if not published.strip():
        raise ValueError("News item has an empty publication timestamp")
    published_at = parse_iso_to_utc(published, default_tz=_CHINA_TZ)
    return {
        "source": source,
        "symbol": symbol,
        "title": title,
        "summary": summary,
        "content": content,
        "url": url,
        "published_at": format_utc_iso(published_at),
    }


def _text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def _optional_text(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None


fetch_a_share_ohlcv_result = as_call_result(
    fetch_a_share_ohlcv,
    map_error=lambda exc: map_requests_error(exc),
)
fetch_global_news_result = as_call_result(
    fetch_global_news,
    map_error=lambda exc: map_requests_error(exc),
)
fetch_stock_news_result = as_call_result(
    fetch_stock_news,
    map_error=lambda exc: map_requests_error(exc),
)
