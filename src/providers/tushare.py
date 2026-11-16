from __future__ import annotations

import asyncio
import math
from datetime import datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pandas as pd

from src.models.result import AppError, as_call_result
from src.providers.base import map_requests_error
from src.utils.time import format_utc_iso, parse_iso_to_utc

_CHINA_TZ = ZoneInfo("Asia/Shanghai")
_SESSION_CLOSE = "15:00:00"
_LOOKBACK_DAYS = 60
_QuoteKind = Literal["stock", "index", "fund"]
_QUOTE_METHOD: dict[_QuoteKind, str] = {
    "stock": "daily",
    "index": "index_daily",
    "fund": "fund_daily",
}
_NAME_METHOD: dict[_QuoteKind, str] = {
    "stock": "stock_basic",
    "index": "index_basic",
    "fund": "fund_basic",
}

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
    """Fetch the latest completed A-share session from Tushare Pro.

    Stocks use ``daily``, Shanghai ``000*`` and Shenzhen ``399*`` indices use
    ``index_daily``, and listed ETFs use ``fund_daily``. ``quote_time`` is that
    session's 15:00 Asia/Shanghai close, not an intraday tick.
    """
    return await asyncio.to_thread(_fetch_a_share_ticker_sync, token=token, symbol=symbol)


def _fetch_a_share_ticker_sync(*, token: str, symbol: str) -> dict[str, Any]:
    import tushare as ts

    kind = _pro_quote_kind(symbol)
    pro = ts.pro_api(token)
    start = (datetime.now(_CHINA_TZ) - timedelta(days=_LOOKBACK_DAYS)).strftime("%Y%m%d")
    df = _query_pro(pro, _QUOTE_METHOD[kind], ts_code=symbol, start_date=start)
    if df is None or df.empty:
        raise AppError("symbol_not_found", f"Tushare returned no ticker for {symbol}")

    df = df.rename(columns={column: str(column).lower() for column in df.columns})
    row = df.sort_values("trade_date").iloc[-1]
    returned_symbol = row.get("ts_code")
    if returned_symbol is not None and not pd.isna(returned_symbol):
        if str(returned_symbol).upper() != symbol.upper():
            raise ValueError(f"Tushare returned ticker {returned_symbol} instead of {symbol}")

    price = _required_number(row, "close")
    if price <= 0:
        raise AppError("no_quote_data", f"Tushare returned no usable price for {symbol}")
    previous_close = _required_number(row, "pre_close")
    change = price - previous_close
    change_percent = change / previous_close * 100 if previous_close else None
    quote_time = parse_iso_to_utc(
        f"{_iso_trade_date(_required_text(row, 'trade_date'))} {_SESSION_CLOSE}",
        default_tz=_CHINA_TZ,
    )
    return {
        "name": _lookup_name(pro, kind, symbol),
        "price": price,
        "previous_close": previous_close,
        "open": _required_number(row, "open"),
        "high": _required_number(row, "high"),
        "low": _required_number(row, "low"),
        "change": change,
        "change_percent": change_percent,
        "quote_time": format_utc_iso(quote_time),
    }


def _pro_quote_kind(symbol: str) -> _QuoteKind:
    """Pick the Pro daily interface that lists this already-suffixed code."""
    code, _, suffix = symbol.upper().partition(".")
    if suffix == "SH" and code.startswith("000"):
        return "index"
    if suffix == "SZ" and code.startswith("399"):
        return "index"
    if suffix == "SH" and code[:2] in {"51", "56", "58"}:
        return "fund"
    if suffix == "SZ" and code[:2] in {"15", "16"}:
        return "fund"
    return "stock"


def _query_pro(pro: Any, method: str, **kwargs: Any) -> pd.DataFrame:
    try:
        return getattr(pro, method)(**kwargs)
    except Exception as exc:
        status = _pro_status(exc)
        if status is not None:
            raise status from exc
        raise


def _lookup_name(pro: Any, kind: _QuoteKind, symbol: str) -> str:
    try:
        df = getattr(pro, _NAME_METHOD[kind])(ts_code=symbol, fields="ts_code,name")
    except Exception as exc:
        if _pro_status(exc) is not None:
            return ""
        raise
    if df is None or df.empty:
        return ""
    df = df.rename(columns={column: str(column).lower() for column in df.columns})
    name = df.iloc[0].get("name")
    if name is None or pd.isna(name):
        return ""
    return str(name)


def _pro_status(exc: Exception) -> AppError | None:
    message = str(exc)
    if "频率" in message or "超限" in message:
        return AppError("provider_rate_limited", message)
    if "权限" in message or "没有接口" in message:
        return AppError("provider_unauthorized", message)
    return None


def _iso_trade_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


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
