from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from src.models.result import as_call_result
from src.providers.base import map_requests_error

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


fetch_a_share_ohlcv_result = as_call_result(
    fetch_a_share_ohlcv,
    map_error=lambda exc: map_requests_error(exc),
)
