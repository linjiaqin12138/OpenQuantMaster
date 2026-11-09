"""Public facades of the application capabilities.

A service groups the UseCases of one capability and exposes them through
semantically named methods. Services own their configuration and the validation
of their public contracts; they never call providers or repositories directly.
"""

from src.services.base import BaseService
from src.services.binance_perp import BinancePerp
from src.services.indicator import Indicator
from src.services.news_fetcher import NewsFetcher
from src.services.notification import NotificationService
from src.services.ohlcv import OHLCV

__all__ = [
    "BaseService",
    "BinancePerp",
    "Indicator",
    "NewsFetcher",
    "NotificationService",
    "OHLCV",
]
