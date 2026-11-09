from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Bar(BaseModel):
    """One OHLCV candle.

    A domain model: it describes market data itself, so it is shared by the
    market-data, indicator, and strategy capabilities instead of being scoped
    to a single request.
    """

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
