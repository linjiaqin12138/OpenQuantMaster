from typing import Any

import pytest

from src.models.result import Error, Result
from src.services.news_fetcher import NewsFetcher


def _news_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "source": "sina",
        "symbol": None,
        "title": "标题",
        "summary": None,
        "content": "央行宣布降息",
        "url": None,
        "published_at": "2026-01-01T19:04:05Z",
    }
    row.update(overrides)
    return row


def _provider(rows: list[dict[str, Any]]):
    async def _call(*args: Any, **kwargs: Any) -> Result:
        return Result(success=True, data=rows)

    return _call


def _failing_provider(code: str):
    async def _call(*args: Any, **kwargs: Any) -> Result:
        return Result(success=False, error=Error(code=code, message="source down"))

    return _call


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_recent_merges_the_items_of_every_source(monkeypatch):
    async def _call(source: str, **kwargs: Any) -> Result:
        return Result(success=True, data=[_news_row(source=source, content=f"{source} 正文")])

    monkeypatch.setattr("src.use_cases.news_fetcher.fetch_global_news_result", _call)

    service = NewsFetcher()
    result = await service.fetch_recent({})

    assert result.success is True
    assert result.data["rows"] == 5
    assert {item["source"] for item in result.data["items"]} == {
        "cls",
        "em",
        "sina",
        "ths",
        "futu",
    }
    assert result.data["coverage"]["earliest"] == "2026-01-01T19:04:05Z"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_recent_filters_the_items_by_keyword(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.news_fetcher.fetch_global_news_result",
        _provider([_news_row(), _news_row(content="指数上涨")]),
    )

    service = NewsFetcher()
    result = await service.fetch_recent({"sources": ["sina"], "keywords": ["降息"]})

    assert result.success is True
    assert result.data["rows"] == 1
    assert result.data["source_stats"]["sina"]["filtered"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_recent_removes_duplicates(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.news_fetcher.fetch_global_news_result",
        _provider([_news_row(), _news_row()]),
    )

    service = NewsFetcher()
    result = await service.fetch_recent({"sources": ["sina"]})

    assert result.data["rows"] == 1
    assert result.data["source_stats"]["sina"]["duplicates"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_recent_reports_a_failing_source(monkeypatch):
    async def _call(source: str, **kwargs: Any) -> Result:
        if source == "cls":
            return Result(
                success=False,
                error=Error(code="provider_unavailable", message="cls down"),
            )
        return Result(success=True, data=[_news_row(source=source)])

    monkeypatch.setattr("src.use_cases.news_fetcher.fetch_global_news_result", _call)

    service = NewsFetcher()
    result = await service.fetch_recent({"sources": ["cls", "sina"]})

    assert result.success is True
    assert result.data["rows"] == 1
    assert result.data["errors"][0]["source"] == "cls"
    assert result.data["errors"][0]["code"] == "news_source_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_recent_fails_when_every_source_fails(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.news_fetcher.fetch_global_news_result",
        _failing_provider("provider_unavailable"),
    )

    service = NewsFetcher()
    result = await service.fetch_recent({"sources": ["cls"]})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "all_sources_failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_stock_news_returns_the_items_of_one_code(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.news_fetcher.fetch_stock_news_result",
        _provider([_news_row(source="em", symbol="603777")]),
    )

    service = NewsFetcher()
    result = await service.fetch_stock_news({"symbol": "603777"})

    assert result.success is True
    assert result.data["rows"] == 1
    assert result.data["items"][0]["symbol"] == "603777"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_stock_news_maps_a_source_failure(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.news_fetcher.fetch_stock_news_result",
        _failing_provider("provider_timeout"),
    )

    service = NewsFetcher()
    result = await service.fetch_stock_news({"symbol": "603777"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "news_source_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_stock_news_rejects_a_missing_symbol():
    service = NewsFetcher()

    result = await service.fetch_stock_news({})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert "symbol" in result.error.message.lower()
