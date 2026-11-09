from __future__ import annotations

import asyncio
import hashlib
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.models.result import ServiceResult
from src.providers.akshare import fetch_global_news_result, fetch_stock_news_result
from src.use_cases.base import BaseUseCase
from src.utils.text import normalize_text

NewsSource = Literal["cls", "em", "sina", "ths", "futu"]

DEFAULT_SOURCES: tuple[str, ...] = ("cls", "em", "sina", "ths", "futu")

_SOURCE_ERROR_CODES = {
    "provider_timeout": "news_source_unavailable",
    "provider_unavailable": "news_source_unavailable",
    "provider_rate_limited": "news_source_unavailable",
}


class FetchRecentNewsInput(BaseModel):
    """Request for the latest flashes of the selected news sources."""

    sources: list[NewsSource] | None = None
    keywords: list[str] = Field(default_factory=list)
    keyword_match: Literal["any", "all"] = "any"
    limit: int | None = Field(default=None, ge=1, le=5000)
    deduplicate: bool = True

    @model_validator(mode="after")
    def normalize_keywords(self) -> FetchRecentNewsInput:
        self.keywords = [keyword.strip() for keyword in self.keywords if keyword.strip()]
        return self


class FetchStockNewsInput(BaseModel):
    """Request for the latest news of one stock code."""

    symbol: str = Field(..., min_length=1)
    limit: int | None = Field(default=None, ge=1, le=5000)


class NewsItem(BaseModel):
    id: str
    source: str
    symbol: str | None = None
    title: str = ""
    summary: str | None = None
    content: str | None = None
    url: str | None = None
    published_at: str


class NewsSourceStats(BaseModel):
    fetched: int = 0
    filtered: int = 0
    duplicates: int = 0
    returned: int = 0


class NewsSourceError(BaseModel):
    source: str
    code: str
    message: str


class NewsCoverage(BaseModel):
    earliest: str | None = None
    latest: str | None = None


class NewsOutput(BaseModel):
    """Response of the news actions."""

    rows: int
    items: list[NewsItem]
    coverage: NewsCoverage
    source_stats: dict[str, NewsSourceStats]
    errors: list[NewsSourceError]


class FetchRecentNewsUseCase(BaseUseCase[FetchRecentNewsInput, NewsOutput]):
    """Fetch the latest flashes of the selected news sources."""

    input_model = FetchRecentNewsInput
    output_model = NewsOutput

    async def _run(self, inputs: FetchRecentNewsInput) -> ServiceResult:
        sources = inputs.sources or list(DEFAULT_SOURCES)
        results = await asyncio.gather(
            *(self._fetch_source(source) for source in sources)
        )
        items: list[NewsItem] = []
        stats: dict[str, NewsSourceStats] = {}
        errors: list[NewsSourceError] = []
        for source, source_items, error in results:
            if error is not None:
                errors.append(error)
                stats[source] = NewsSourceStats()
            else:
                stats[source] = NewsSourceStats(fetched=len(source_items))
                items.extend(source_items)
        if len(errors) == len(sources):
            return ServiceResult.from_error(
                "all_sources_failed",
                "All news sources failed",
            )
        return _build_output(inputs, items, stats, errors)

    async def _fetch_source(
        self,
        source: str,
    ) -> tuple[str, list[NewsItem], NewsSourceError | None]:
        result = await fetch_global_news_result(source)
        if not result.success:
            error = result.error
            code = (
                _SOURCE_ERROR_CODES.get(error.code, "news_source_failed")
                if error
                else "news_source_failed"
            )
            return (
                source,
                [],
                NewsSourceError(
                    source=source,
                    code=code,
                    message=error.message if error else "unknown error",
                ),
            )
        return source, [_to_item(row) for row in result.data], None


class FetchStockNewsUseCase(BaseUseCase[FetchStockNewsInput, NewsOutput]):
    """Fetch the latest news of one stock code."""

    input_model = FetchStockNewsInput
    output_model = NewsOutput

    async def _run(self, inputs: FetchStockNewsInput) -> ServiceResult:
        result = await fetch_stock_news_result(inputs.symbol)
        if not result.success:
            error = result.error
            code = (
                _SOURCE_ERROR_CODES.get(error.code, "news_source_failed")
                if error
                else "news_source_failed"
            )
            return ServiceResult.from_error(
                code,
                f"eastmoney: {error.message if error else 'unknown error'}",
                error.exception if error else None,
            )
        items = [_to_item(row) for row in result.data]
        return _build_output(
            inputs,
            items,
            {"em": NewsSourceStats(fetched=len(items))},
            [],
        )


def _to_item(row: dict[str, Any]) -> NewsItem:
    identity = row.get("url") or "|".join(
        (
            row.get("published_at", ""),
            row.get("title", ""),
            row.get("summary") or "",
            row.get("content") or "",
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return NewsItem(
        id=f"{row.get('source', 'unknown')}_{digest}",
        source=row.get("source", ""),
        symbol=row.get("symbol"),
        title=row.get("title", ""),
        summary=row.get("summary"),
        content=row.get("content"),
        url=row.get("url"),
        published_at=row.get("published_at", ""),
    )


def _build_output(
    inputs: FetchRecentNewsInput | FetchStockNewsInput,
    items: list[NewsItem],
    stats: dict[str, NewsSourceStats],
    errors: list[NewsSourceError],
) -> ServiceResult:
    filtered_items: list[NewsItem] = []
    for item in items:
        if _matches_keywords(item, inputs):
            filtered_items.append(item)
        else:
            stats[item.source].filtered += 1

    filtered_items.sort(
        key=lambda item: (item.published_at, bool(item.title), bool(item.url), item.id),
        reverse=True,
    )
    if getattr(inputs, "deduplicate", True):
        unique_items: list[NewsItem] = []
        seen: set[tuple[str, str, str]] = set()
        for item in filtered_items:
            key = (
                normalize_text(item.title),
                normalize_text(item.summary or ""),
                normalize_text(item.content or ""),
            )
            if key in seen:
                stats[item.source].duplicates += 1
                continue
            seen.add(key)
            unique_items.append(item)
        filtered_items = unique_items

    if inputs.limit is not None:
        filtered_items = filtered_items[: inputs.limit]
    for item in filtered_items:
        stats[item.source].returned += 1

    timestamps = [item.published_at for item in filtered_items]
    output = NewsOutput(
        rows=len(filtered_items),
        items=filtered_items,
        coverage=NewsCoverage(
            earliest=min(timestamps) if timestamps else None,
            latest=max(timestamps) if timestamps else None,
        ),
        source_stats=stats,
        errors=errors,
    )
    return ServiceResult(success=True, data=output)


def _matches_keywords(
    item: NewsItem,
    inputs: FetchRecentNewsInput | FetchStockNewsInput,
) -> bool:
    keywords = getattr(inputs, "keywords", [])
    if not keywords:
        return True
    match = getattr(inputs, "keyword_match", "any")
    haystack = " ".join((item.title, item.summary or "", item.content or "")).casefold()
    checks = (keyword.casefold() in haystack for keyword in keywords)
    return any(checks) if match == "any" else all(checks)
