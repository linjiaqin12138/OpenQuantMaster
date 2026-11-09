from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from src.models.result import as_call_result
from src.providers.base import map_requests_error

_COLUMN_MAP = {
    "Date": "timestamp",
    "Datetime": "timestamp",
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}


async def fetch_equity_ohlcv(
    *,
    symbol: str,
    interval: str,
    limit: int = 1000,
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch OHLCV bars for a US/HK equity through yfinance."""
    return await asyncio.to_thread(
        _fetch_equity_ohlcv_sync,
        symbol=symbol,
        interval=interval,
        limit=limit,
        start=start,
        end=end,
    )


def _fetch_equity_ohlcv_sync(
    *,
    symbol: str,
    interval: str,
    limit: int,
    start: str | None,
    end: str | None,
) -> list[dict[str, Any]]:
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    kwargs: dict[str, Any] = {"interval": interval}
    if start:
        kwargs["start"] = start[:10]
    if end:
        kwargs["end"] = end[:10]
    if not kwargs.get("start"):
        kwargs["period"] = "max" if limit > 100 else "1y"

    hist = ticker.history(**kwargs).reset_index().rename(columns=_COLUMN_MAP)
    hist["timestamp"] = pd.to_datetime(hist["timestamp"], utc=True)
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    bars = hist[columns].to_dict(orient="records")
    for bar in bars:
        bar["timestamp"] = pd.Timestamp(bar["timestamp"]).isoformat()
    return bars


fetch_equity_ohlcv_result = as_call_result(
    fetch_equity_ohlcv,
    map_error=lambda exc: map_requests_error(exc),
)
