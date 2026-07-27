from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from runtime.config_loader import OpenAliceConfig
from runtime.openalice_client import OpenAliceClient, OpenAliceError
from tools.news.news_filter_tool import NewsFilterTool


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\nenvironment: testing\n",
        encoding="utf-8",
    )


def _make_article(article_id: int, title: str, source: str = "scmp-business") -> dict:
    metadata = {"source": source, "link": f"https://example.com/{article_id}"}
    return {
        "id": article_id,
        "time": "2026-07-27T12:00:00Z",
        "title": title,
        "metadata": json.dumps(metadata),
    }


def _make_llm_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def _build_tool(
    tmp_path: Path, client: AsyncMock, notifier: AsyncMock | None = None
) -> NewsFilterTool:
    return NewsFilterTool(
        artifacts_path=tmp_path / "artifacts",
        openalice_client=client,
        notifier=notifier or AsyncMock(),
        watch_state_path=tmp_path / "watch_state.json",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_scores_and_bins_articles(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [
        _make_article(770, "Bitcoin ETF approved"),
        _make_article(771, "Local bakery wins award"),
        _make_article(772, "Exchange hack reported"),
    ]
    client = AsyncMock()
    client.window_rss = AsyncMock(
        return_value={"total": 3, "shown": 3, "omitted": 0, "results": articles}
    )

    llm_responses = [
        _make_llm_response('{"score": 0.85, "reason": "ETF approval is bullish"}'),
        _make_llm_response('{"score": 0.2, "reason": "Not relevant"}'),
        _make_llm_response("not valid json"),
    ]

    tool = _build_tool(tmp_path, client)
    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(side_effect=llm_responses),
    ):
        result = await tool.execute({"window_minutes": 60, "limit": 10})

    assert result.success is True
    data = result.data
    assert data["total"] == 3
    assert data["new"] == 3
    assert data["scored"] == 2
    assert len(data["high"]) == 1
    assert data["high"][0]["id"] == "770"
    assert data["high"][0]["score"] == 0.85
    assert len(data["medium_pending"]) == 0
    assert len(data["degraded"]) == 1
    assert data["degraded"][0]["id"] == "772"
    assert "LLM parse error" in data["degraded"][0]["error"]

    state_path = tmp_path / "watch_state.json"
    assert state_path.exists()
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(state["news_filter"]["seen_ids"]) == {"770", "771", "772"}
    assert "last_run_at" in state["news_filter"]

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.name == "news_filter_result.json"
    saved = json.loads(artifact.content)
    assert saved["total"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_bins_medium_pending(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [
        _make_article(880, "Regulatory hearing next week"),
        _make_article(881, "Stablecoin depeg rumors"),
    ]
    client = AsyncMock()
    client.window_rss = AsyncMock(
        return_value={"total": 2, "shown": 2, "omitted": 0, "results": articles}
    )

    responses = [
        _make_llm_response('{"score": 0.45, "reason": "Potential volatility"}'),
        _make_llm_response('{"score": 0.75, "reason": "Depeg risk"}'),
    ]

    tool = _build_tool(tmp_path, client)
    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(side_effect=responses),
    ):
        result = await tool.execute({"window_minutes": 60, "limit": 10})

    assert result.success is True
    data = result.data
    assert len(data["high"]) == 1
    assert data["high"][0]["id"] == "881"
    assert len(data["medium_pending"]) == 1
    assert data["medium_pending"][0]["id"] == "880"
    assert data["scored"] == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_openalice_error_returns_failure(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    client = AsyncMock()
    client.window_rss = AsyncMock(side_effect=OpenAliceError("gateway down"))

    tool = _build_tool(tmp_path, client)
    result = await tool.execute({"window_minutes": 60})

    assert result.success is False
    assert "OpenAlice" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_llm_failure_notifies_and_fails(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(990, "Major exploit")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    notifier = AsyncMock()
    notifier.send = AsyncMock(return_value={"pushplus": "ok"})

    tool = _build_tool(tmp_path, client, notifier)
    # Bypass the tenacity retry wrapper to keep the test fast.
    tool._call_litellm = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    result = await tool.execute({"window_minutes": 60})

    assert result.success is False
    assert "LLM scoring failed" in result.error
    notifier.send.assert_awaited_once()
    call = notifier.send.await_args
    assert "news_filter_tool LLM failure" in call.kwargs["subject"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_skips_seen_articles(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(100, "First article")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})

    notifier = AsyncMock()
    tool = _build_tool(tmp_path, client, notifier)

    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(
            return_value=_make_llm_response('{"score": 0.9, "reason": "Big news"}')
        ),
    ):
        first = await tool.execute({"window_minutes": 60})
    assert first.data["new"] == 1

    # Second run with the same returned article should mark it as already seen.
    second = await tool.execute({"window_minutes": 60})
    assert second.data["total"] == 1
    assert second.data["new"] == 0
    assert second.data["scored"] == 0
    assert second.data["high"] == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_merges_watch_state(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    existing = {"other_tool": {"counter": 5}}
    (tmp_path / "watch_state.json").write_text(json.dumps(existing), encoding="utf-8")

    articles = [_make_article(200, "Merge test")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})

    tool = _build_tool(tmp_path, client)
    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(return_value=_make_llm_response('{"score": 0.95, "reason": "Merge"}')),
    ):
        result = await tool.execute({"window_minutes": 60})

    assert result.success is True
    state = json.loads((tmp_path / "watch_state.json").read_text(encoding="utf-8"))
    assert state["other_tool"]["counter"] == 5
    assert "200" in state["news_filter"]["seen_ids"]


@pytest.mark.unit
def test_parse_article_falls_back_to_regex_on_truncated_metadata():
    article = {
        "id": 999,
        "time": "2026-07-27T10:00:00Z",
        "title": "Truncated article",
        "metadata": '{"source":"cnbc-economy","link":"http://example.com/very-long-link-that-was-cut...',
    }
    parsed = NewsFilterTool._parse_article(article)
    assert parsed["source"] == "cnbc-economy"
    assert parsed["link"].startswith("http://example.com/very-long-link-that-was-cut")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openalice_client_parses_content_text():
    inner = {
        "from": "2026-07-26",
        "to": "2026-07-27",
        "total": 1,
        "shown": 1,
        "omitted": 0,
        "results": [
            {
                "id": 770,
                "time": "2026-07-26T00:00:14Z",
                "title": "Headline",
                "metadata": "{}",
            }
        ],
    }
    gateway_response = {"content": [{"type": "text", "text": json.dumps(inner)}]}

    mock_post = AsyncMock(return_value=MagicMock())
    mock_response = mock_post.return_value
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=gateway_response)

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = mock_post

    config = OpenAliceConfig(
        workspace_id="auto-quant-clear-willow-field",
        cli_gateway_url="http://127.0.0.1:47332",
        export="data",
    )
    client = OpenAliceClient(config, timeout=5.0)

    with patch("runtime.openalice_client.httpx.AsyncClient", return_value=mock_http):
        result = await client.window_rss(from_time="2026-07-26", limit=1)

    assert result["total"] == 1
    assert result["results"][0]["id"] == 770
    mock_post.assert_awaited_once()
    call = mock_post.await_args
    assert call.kwargs["json"]["tool"] == "windowRss"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_openalice_client_raises_on_http_error():
    mock_post = AsyncMock(side_effect=httpx.HTTPError("gateway down"))

    mock_http = AsyncMock()
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=None)
    mock_http.post = mock_post

    config = OpenAliceConfig(cli_gateway_url="http://127.0.0.1:47332")
    client = OpenAliceClient(config, timeout=5.0)

    with patch("runtime.openalice_client.httpx.AsyncClient", return_value=mock_http):
        with pytest.raises(OpenAliceError):
            await client.window_rss(from_time="2026-07-26", limit=1)
