from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime
from typing import Any, ClassVar, Literal
from zoneinfo import ZoneInfo

import akshare as ak
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from src.services.base import BaseService, ServiceResult

NewsSource = Literal["cls", "em", "sina", "ths", "futu"]
DEFAULT_SOURCES: tuple[NewsSource, ...] = ("cls", "em", "sina", "ths", "futu")
_SOURCE_FUNCTIONS = {
    "cls": "stock_info_global_cls",
    "em": "stock_info_global_em",
    "sina": "stock_info_global_sina",
    "ths": "stock_info_global_ths",
    "futu": "stock_info_global_futu",
}
_CHINA_TZ = ZoneInfo("Asia/Shanghai")


class NewsInput(BaseModel):
    mode: Literal["recent", "stock_recent"] = "recent"
    sources: list[NewsSource] | None = None
    symbol: str | None = None
    keywords: list[str] = Field(default_factory=list)
    keyword_match: Literal["any", "all"] = "any"
    limit: int | None = Field(default=None, ge=1, le=5000)
    deduplicate: bool = True

    @model_validator(mode="after")
    def validate_mode_params(self) -> NewsInput:
        if self.mode == "stock_recent":
            if not self.symbol:
                raise ValueError("symbol is required when mode=stock_recent")
            if self.sources is not None:
                raise ValueError("sources is not supported when mode=stock_recent")
        elif self.symbol is not None:
            raise ValueError("symbol is only supported when mode=stock_recent")
        self.keywords = [keyword.strip() for keyword in self.keywords if keyword.strip()]
        return self


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
    mode: str
    rows: int
    items: list[NewsItem]
    coverage: NewsCoverage
    source_stats: dict[str, NewsSourceStats]
    errors: list[NewsSourceError]


class NewsFetcher(BaseService):
    input_model: ClassVar[type[BaseModel]] = NewsInput
    output_model: ClassVar[type[BaseModel]] = NewsOutput

    async def _run(self, inputs: NewsInput) -> ServiceResult:
        if inputs.mode == "stock_recent":
            return await self._run_stock_recent(inputs)
        return await self._run_recent(inputs)

    async def _run_recent(self, inputs: NewsInput) -> ServiceResult:
        sources = inputs.sources or list(DEFAULT_SOURCES)
        results = await asyncio.gather(*(self._fetch_recent_source(source) for source in sources))
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
            return ServiceResult.from_error("all_sources_failed", "All news sources failed")
        return self._build_result(inputs, items, stats, errors)

    async def _run_stock_recent(self, inputs: NewsInput) -> ServiceResult:
        assert inputs.symbol is not None
        try:
            df = await asyncio.to_thread(ak.stock_news_em, symbol=inputs.symbol)
            items = [_normalize_stock_row(row, inputs.symbol) for row in df.to_dict(orient="records")]
        except Exception as exc:
            return ServiceResult.from_error("source_fetch_failed", f"eastmoney: {exc}", exc)
        return self._build_result(
            inputs,
            items,
            {"em": NewsSourceStats(fetched=len(items))},
            [],
        )

    async def _fetch_recent_source(
        self, source: NewsSource
    ) -> tuple[NewsSource, list[NewsItem], NewsSourceError | None]:
        try:
            function = getattr(ak, _SOURCE_FUNCTIONS[source])
            df = await asyncio.to_thread(function)
            items = [_normalize_recent_row(source, row) for row in df.to_dict(orient="records")]
            return source, items, None
        except Exception as exc:
            return source, [], NewsSourceError(
                source=source,
                code="source_fetch_failed",
                message=str(exc),
            )

    def _build_result(
        self,
        inputs: NewsInput,
        items: list[NewsItem],
        stats: dict[str, NewsSourceStats],
        errors: list[NewsSourceError],
    ) -> ServiceResult:
        filtered_items: list[NewsItem] = []
        for item in items:
            if _matches_keywords(item, inputs.keywords, inputs.keyword_match):
                filtered_items.append(item)
            else:
                stats[item.source].filtered += 1

        filtered_items.sort(
            key=lambda item: (item.published_at, bool(item.title), bool(item.url), item.id),
            reverse=True,
        )
        if inputs.deduplicate:
            unique_items: list[NewsItem] = []
            seen: set[tuple[str, str, str]] = set()
            for item in filtered_items:
                key = (
                    _normalize_text(item.title),
                    _normalize_text(item.summary or ""),
                    _normalize_text(item.content or ""),
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
        output = self.output_model(
            mode=inputs.mode,
            rows=len(filtered_items),
            items=filtered_items,
            coverage=NewsCoverage(
                earliest=min(timestamps) if timestamps else None,
                latest=max(timestamps) if timestamps else None,
            ),
            source_stats=stats,
            errors=errors,
        )
        return ServiceResult(success=True, data=output.model_dump())


def _normalize_recent_row(source: NewsSource, row: dict[str, Any]) -> NewsItem:
    if source == "cls":
        published = f"{_text(row.get('发布日期'))} {_text(row.get('发布时间'))}"
        title = _text(row.get("标题"))
        content = _text(row.get("内容"))
        summary = None
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
    return _make_item(source, None, title, summary, content, url, published)


def _normalize_stock_row(row: dict[str, Any], symbol: str) -> NewsItem:
    return _make_item(
        "em",
        symbol,
        _text(row.get("新闻标题")),
        None,
        _optional_text(row.get("新闻内容")),
        _optional_text(row.get("新闻链接")),
        _text(row.get("发布时间")),
    )


def _make_item(
    source: str,
    symbol: str | None,
    title: str,
    summary: str | None,
    content: str | None,
    url: str | None,
    published: str,
) -> NewsItem:
    published_at = _parse_china_timestamp(published)
    identity = url or f"{published_at}|{title}|{summary or ''}|{content or ''}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return NewsItem(
        id=f"{source}_{digest}",
        source=source,
        symbol=symbol,
        title=title,
        summary=summary,
        content=content,
        url=url,
        published_at=published_at,
    )


def _parse_china_timestamp(value: str) -> str:
    if not value.strip():
        raise ValueError("News item has an empty publication timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Unsupported news publication timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_CHINA_TZ)
    return parsed.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def _matches_keywords(item: NewsItem, keywords: list[str], match: str) -> bool:
    if not keywords:
        return True
    haystack = " ".join((item.title, item.summary or "", item.content or "")).casefold()
    checks = (keyword.casefold() in haystack for keyword in keywords)
    return any(checks) if match == "any" else all(checks)


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _text(value: Any) -> str:
    return "" if value is None or pd.isna(value) else str(value)


def _optional_text(value: Any) -> str | None:
    text = _text(value).strip()
    return text or None
