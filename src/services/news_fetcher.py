from __future__ import annotations

from typing import Any

from src.models.result import ServiceResult
from src.services.base import BaseService
from src.use_cases.news_fetcher import (
    FetchRecentNewsInput,
    FetchRecentNewsUseCase,
    FetchStockNewsInput,
    FetchStockNewsUseCase,
    NewsOutput,
)

__all__ = [
    "FetchRecentNewsInput",
    "FetchStockNewsInput",
    "NewsOutput",
    "NewsFetcher",
]


class NewsFetcher(BaseService):
    """News capability: recent financial news across several sources."""

    def __init__(self) -> None:
        self._fetch_recent = FetchRecentNewsUseCase()
        self._fetch_stock_news = FetchStockNewsUseCase()

    async def fetch_recent(
        self,
        request: FetchRecentNewsInput | dict[str, Any],
    ) -> ServiceResult:
        """Fetch the latest flashes of the selected news sources."""
        return await self._fetch_recent.run(request)

    async def fetch_stock_news(
        self,
        request: FetchStockNewsInput | dict[str, Any],
    ) -> ServiceResult:
        """Fetch the latest news of one stock code."""
        return await self._fetch_stock_news.run(request)
