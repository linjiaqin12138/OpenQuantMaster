from __future__ import annotations

import asyncio
import math
import os
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from src.models.result import AppError, as_call_result
from src.providers.base import map_requests_error
from src.utils.time import format_utc_iso, parse_iso_to_utc

_CHINA_TZ = ZoneInfo("Asia/Shanghai")

_COLUMN_MAP = {
    "trade_date": "timestamp",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "vol": "volume",
}


async def fetch_a_share_ohlcv(
    *,
    token: str,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch daily bars for an A-share code through Tushare."""
    return await asyncio.to_thread(
        _fetch_a_share_ohlcv_sync,
        token=token,
        symbol=symbol,
        start=start,
        end=end,
    )


def _fetch_a_share_ohlcv_sync(
    *,
    token: str,
    symbol: str,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    import tushare as ts

    pro = ts.pro_api(token)
    start_date = (start or "")[:10].replace("-", "")
    end_date = (end or "")[:10].replace("-", "")
    df = pro.daily(
        ts_code=symbol,
        start_date=start_date or None,
        end_date=end_date or None,
    )
    df = df.rename(columns=_COLUMN_MAP)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y%m%d", utc=True)
    df = df[["timestamp", "open", "high", "low", "close", "volume"]]
    df = df.sort_values("timestamp").reset_index(drop=True)
    bars = df.to_dict(orient="records")
    for bar in bars:
        bar["timestamp"] = pd.Timestamp(bar["timestamp"]).isoformat()
    return bars


async def fetch_a_share_ticker(*, token: str, symbol: str) -> dict[str, Any]:
    """Fetch the latest snapshot for an A-share code through Tushare."""
    return await asyncio.to_thread(_fetch_a_share_ticker_sync, token=token, symbol=symbol)


def _fetch_a_share_ticker_sync(*, token: str, symbol: str) -> dict[str, Any]:
    import tushare as ts

    previous_token = os.environ.get("TUSHARE_TOKEN")
    os.environ["TUSHARE_TOKEN"] = token
    try:
        df = ts.realtime_quote(ts_code=symbol, src="sina")
    finally:
        if previous_token is None:
            os.environ.pop("TUSHARE_TOKEN", None)
        else:
            os.environ["TUSHARE_TOKEN"] = previous_token

    if df is None or df.empty:
        raise AppError("symbol_not_found", f"Tushare returned no ticker for {symbol}")
    if len(df) != 1:
        raise ValueError(f"Tushare returned {len(df)} ticker rows for {symbol}")

    df = df.rename(columns={column: str(column).lower() for column in df.columns})
    row = df.iloc[0]
    returned_symbol = row.get("ts_code")
    if returned_symbol is not None and not pd.isna(returned_symbol):
        if str(returned_symbol).upper() != symbol.upper():
            raise ValueError(f"Tushare returned ticker {returned_symbol} instead of {symbol}")

    quote_date = _required_text(row, "date")
    if len(quote_date) == 8 and quote_date.isdigit():
        quote_date = f"{quote_date[:4]}-{quote_date[4:6]}-{quote_date[6:]}"
    quote_clock = _required_text(row, "time")
    quote_time = parse_iso_to_utc(f"{quote_date} {quote_clock}", default_tz=_CHINA_TZ)
    price = _required_number(row, "price")
    if price <= 0:
        raise AppError("no_quote_data", f"Tushare returned no usable price for {symbol}")
    previous_close = _required_number(row, "pre_close")
    change = price - previous_close
    change_percent = change / previous_close * 100 if previous_close else None

    return {
        "name": "" if pd.isna(row.get("name")) else str(row.get("name")),
        "price": price,
        "previous_close": previous_close,
        "open": _required_number(row, "open"),
        "high": _required_number(row, "high"),
        "low": _required_number(row, "low"),
        "change": change,
        "change_percent": change_percent,
        "quote_time": format_utc_iso(quote_time),
    }


def _required_text(row: pd.Series, column: str) -> str:
    value = row.get(column)
    if value is None or pd.isna(value) or not str(value).strip():
        raise ValueError(f"Tushare ticker is missing {column}")
    return str(value).strip()


def _required_number(row: pd.Series, column: str) -> float:
    value = row.get(column)
    if value is None or pd.isna(value):
        raise ValueError(f"Tushare ticker is missing {column}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"Tushare ticker has a non-finite {column}")
    return number


fetch_a_share_ohlcv_result = as_call_result(
    fetch_a_share_ohlcv,
    map_error=lambda exc: map_requests_error(exc),
)
fetch_a_share_ticker_result = as_call_result(
    fetch_a_share_ticker,
    map_error=lambda exc: map_requests_error(exc),
)
