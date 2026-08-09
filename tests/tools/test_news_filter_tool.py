from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from runtime.config_loader import OpenAliceConfig, get_llm_config
from runtime.openalice_client import OpenAliceClient, OpenAliceError
from tools.news.news_filter_tool import NewsFilterTool


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\nenvironment: testing\n",
        encoding="utf-8",
    )


def _make_article(article_id: int, title: str, source: str = "scmp-business") -> dict:
    """WindowRss-style article with truncated JSON-string metadata."""
    metadata = {"source": source, "link": f"https://example.com/{article_id}"}
    return {
        "id": article_id,
        "time": "2026-07-27T12:00:00Z",
        "title": title,
        "metadata": json.dumps(metadata),
    }


def _make_full_article(article_id: int, title: str, source: str = "scmp-business") -> dict:
    """ReadRss-style full article with dict metadata."""
    return {
        "id": article_id,
        "time": "2026-07-27T12:00:00Z",
        "title": title,
        "content": f"Full content for {title}",
        "metadata": {
            "source": source,
            "link": f"https://example.com/{article_id}?utm_source=rss_feed&very_long_parameter=1",
        },
    }


def _make_llm_response(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


def _build_tool(
    tmp_path: Path, client: AsyncMock
) -> NewsFilterTool:
    return NewsFilterTool(
        artifacts_path=tmp_path / "artifacts",
        openalice_client=client,
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
    client.read_rss = AsyncMock(
        side_effect=[
            _make_full_article(770, "Bitcoin ETF approved"),
            _make_full_article(771, "Local bakery wins award"),
            _make_full_article(772, "Exchange hack reported"),
        ]
    )

    llm_responses = [
        _make_llm_response('{"ratings": [{"id": "770", "score": 0.85, "reason": "ETF approval is bullish"}]}'),
        _make_llm_response('{"ratings": [{"id": "771", "score": 0.2, "reason": "Not relevant"}]}'),
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
    assert "LLM batch parse error" in data["degraded"][0]["error"]

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
    client.read_rss = AsyncMock(
        side_effect=[
            _make_full_article(880, "Regulatory hearing next week"),
            _make_full_article(881, "Stablecoin depeg rumors"),
        ]
    )

    responses = [
        _make_llm_response('{"ratings": [{"id": "880", "score": 0.45, "reason": "Potential volatility"}]}'),
        _make_llm_response('{"ratings": [{"id": "881", "score": 0.75, "reason": "Depeg risk"}]}'),
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
async def test_news_filter_llm_failure_fails(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(990, "Major exploit")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    client.read_rss = AsyncMock(return_value=_make_full_article(990, "Major exploit"))

    tool = _build_tool(tmp_path, client)
    # Bypass the tenacity retry wrapper to keep the test fast.
    tool._call_litellm = AsyncMock(side_effect=RuntimeError("LLM timeout"))

    result = await tool.execute({"window_minutes": 60})

    assert result.success is False
    assert "LLM scoring failed" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_skips_seen_articles(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(100, "First article")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    client.read_rss = AsyncMock(return_value=_make_full_article(100, "First article"))

    tool = _build_tool(tmp_path, client)

    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(
            return_value=_make_llm_response('{"ratings": [{"id": "100", "score": 0.9, "reason": "Big news"}]}')
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
    client.read_rss = AsyncMock(return_value=_make_full_article(200, "Merge test"))

    tool = _build_tool(tmp_path, client)
    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(return_value=_make_llm_response('{"ratings": [{"id": "200", "score": 0.95, "reason": "Merge"}]}')),
    ):
        result = await tool.execute({"window_minutes": 60})

    assert result.success is True
    state = json.loads((tmp_path / "watch_state.json").read_text(encoding="utf-8"))
    assert state["other_tool"]["counter"] == 5
    assert "200" in state["news_filter"]["seen_ids"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_uses_config_prompt_template(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\n"
        "environment: testing\n"
        "tools:\n"
        "  news_filter_tool:\n"
        "    prompt:\n"
        "      template: |\n"
        "        You are a U.S. equities risk analyst. Return ONLY JSON.\n"
        "        {articles}\n",
        encoding="utf-8",
    )

    articles = [_make_article(301, "Fed raises rates")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    client.read_rss = AsyncMock(return_value=_make_full_article(301, "Fed raises rates"))

    mock_llm = AsyncMock(
        return_value=_make_llm_response('{"ratings": [{"id": "301", "score": 0.8, "reason": "Macro event"}]}')
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute({"window_minutes": 60})

    assert result.success is True
    prompt = mock_llm.await_args.kwargs["messages"][0]["content"]
    assert "U.S. equities risk analyst" in prompt
    assert "crypto trading risk analyst" not in prompt
    assert "Title: Fed raises rates" in prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_input_prompt_template_overrides_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\n"
        "environment: testing\n"
        "tools:\n"
        "  news_filter_tool:\n"
        "    prompt:\n"
        "      template: 'config template {articles}'\n",
        encoding="utf-8",
    )

    articles = [_make_article(302, "Override test")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    client.read_rss = AsyncMock(return_value=_make_full_article(302, "Override test"))

    mock_llm = AsyncMock(
        return_value=_make_llm_response('{"ratings": [{"id": "302", "score": 0.9, "reason": "ok"}]}')
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute(
            {"window_minutes": 60, "prompt_template": "input template {articles}"}
        )

    assert result.success is True
    prompt = mock_llm.await_args.kwargs["messages"][0]["content"]
    assert prompt.startswith("input template ")
    assert "[Article id=302]" in prompt
    assert "Title: Override test" in prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_unknown_placeholder_fails_loud(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    client = AsyncMock()
    mock_llm = AsyncMock()
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute(
            {"window_minutes": 60, "prompt_template": "Rate this {summary} article {title}"}
        )

    assert result.success is False
    assert "summary" in result.error
    assert "unknown placeholder" in result.error
    client.window_rss.assert_not_awaited()
    mock_llm.assert_not_awaited()


def _make_batch_response(ratings: list[tuple[str, float, str]]) -> MagicMock:
    payload = {"ratings": [{"id": i, "score": s, "reason": r} for i, s, r in ratings]}
    return _make_llm_response(json.dumps(payload))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_batches_articles(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(900 + i, f"Batch article {i}") for i in range(1, 13)]
    client = AsyncMock()
    client.window_rss = AsyncMock(
        return_value={"total": 12, "shown": 12, "omitted": 0, "results": articles}
    )
    client.read_rss = AsyncMock(
        side_effect=[_make_full_article(900 + i, f"Batch article {i}") for i in range(1, 13)]
    )

    mock_llm = AsyncMock(
        side_effect=[
            _make_batch_response(
                [("901", 0.9, "high")] + [(str(900 + i), 0.1, "low") for i in range(2, 6)]
            ),
            _make_batch_response(
                [("907", 0.5, "medium")] + [(str(900 + i), 0.1, "low") for i in (6, 8, 9, 10)]
            ),
            _make_batch_response([(str(900 + i), 0.1, "low") for i in range(11, 13)]),
        ]
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute({"window_minutes": 60, "batch_size": 5})

    assert result.success is True
    assert mock_llm.await_count == 3  # ceil(12 / 5)
    data = result.data
    assert data["scored"] == 12
    assert [a["id"] for a in data["high"]] == ["901"]
    assert [a["id"] for a in data["medium_pending"]] == ["907"]

    first_prompt = mock_llm.await_args_list[0].kwargs["messages"][0]["content"]
    assert "[Article id=901]" in first_prompt
    assert "[Article id=905]" in first_prompt
    assert "Articles (5)" in first_prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_batch_missing_id_degraded(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(950 + i, f"Missing id {i}") for i in range(3)]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 3, "results": articles})
    client.read_rss = AsyncMock(
        side_effect=[_make_full_article(950 + i, f"Missing id {i}") for i in range(3)]
    )

    mock_llm = AsyncMock(
        return_value=_make_batch_response([("950", 0.9, "high"), ("952", 0.8, "high")])
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute({"window_minutes": 60, "batch_size": 5})

    assert result.success is True
    data = result.data
    assert data["scored"] == 2
    assert {a["id"] for a in data["high"]} == {"950", "952"}
    assert len(data["degraded"]) == 1
    assert data["degraded"][0]["id"] == "951"
    assert "missing from LLM batch response" in data["degraded"][0]["error"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_batch_parse_error_degrades_whole_batch(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(960 + i, f"Parse error {i}") for i in range(4)]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 4, "results": articles})
    client.read_rss = AsyncMock(
        side_effect=[_make_full_article(960 + i, f"Parse error {i}") for i in range(4)]
    )

    mock_llm = AsyncMock(return_value=_make_llm_response("totally not json"))
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute({"window_minutes": 60, "batch_size": 5})

    assert result.success is True
    data = result.data
    assert data["scored"] == 0
    assert len(data["degraded"]) == 4
    assert all("LLM batch parse error" in a["error"] for a in data["degraded"])


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_batch_size_from_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\n"
        "environment: testing\n"
        "tools:\n"
        "  news_filter_tool:\n"
        "    batch_size: 5\n",
        encoding="utf-8",
    )

    articles = [_make_article(970 + i, f"Config batch {i}") for i in range(7)]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 7, "results": articles})
    client.read_rss = AsyncMock(
        side_effect=[_make_full_article(970 + i, f"Config batch {i}") for i in range(7)]
    )

    mock_llm = AsyncMock(
        side_effect=[
            _make_batch_response([(str(970 + i), 0.1, "low") for i in range(5)]),
            _make_batch_response([(str(970 + i), 0.1, "low") for i in range(5, 7)]),
        ]
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute({"window_minutes": 60})

    assert result.success is True
    assert mock_llm.await_count == 2  # ceil(7 / 5), batch_size from config


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_input_batch_size_overrides_config(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\n"
        "environment: testing\n"
        "tools:\n"
        "  news_filter_tool:\n"
        "    batch_size: 5\n",
        encoding="utf-8",
    )

    articles = [_make_article(980 + i, f"Override batch {i}") for i in range(5)]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 5, "results": articles})
    client.read_rss = AsyncMock(
        side_effect=[_make_full_article(980 + i, f"Override batch {i}") for i in range(5)]
    )

    mock_llm = AsyncMock(
        side_effect=[
            _make_batch_response([(str(980 + i), 0.1, "low") for i in range(2)]),
            _make_batch_response([(str(980 + i), 0.1, "low") for i in range(2, 4)]),
            _make_batch_response([("984", 0.1, "low")]),
        ]
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute({"window_minutes": 60, "batch_size": 2})

    assert result.success is True
    assert mock_llm.await_count == 3  # ceil(5 / 2), input overrides config batch_size=5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_custom_batch_template_renders_all_articles(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(990 + i, f"Template {i}") for i in range(2)]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 2, "results": articles})
    client.read_rss = AsyncMock(
        side_effect=[_make_full_article(990 + i, f"Template {i}") for i in range(2)]
    )

    mock_llm = AsyncMock(
        return_value=_make_batch_response([("990", 0.9, "a"), ("991", 0.2, "b")])
    )
    tool = _build_tool(tmp_path, client)
    with patch("tools.news.news_filter_tool.litellm.acompletion", new=mock_llm):
        result = await tool.execute(
            {
                "window_minutes": 60,
                "batch_size": 5,
                "prompt_template": "Custom equities template, {count} items:\n{articles}",
            }
        )

    assert result.success is True
    prompt = mock_llm.await_args.kwargs["messages"][0]["content"]
    assert prompt.startswith("Custom equities template, 2 items:")
    assert "[Article id=990]" in prompt
    assert "[Article id=991]" in prompt


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
def test_parse_article_uses_dict_metadata_directly():
    article = {
        "id": 888,
        "time": "2026-07-27T10:00:00Z",
        "title": "Full article",
        "metadata": {
            "source": "reuters",
            "link": "https://reuters.com/article/12345?utm_source=rss",
        },
        "content": "Full text here",
    }
    parsed = NewsFilterTool._parse_article(article)
    assert parsed["source"] == "reuters"
    assert parsed["link"] == "https://reuters.com/article/12345?utm_source=rss"
    assert parsed["content"] == "Full text here"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_enriches_articles_with_read_rss(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(555, "Enrichment test")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    full = _make_full_article(555, "Enrichment test")
    client.read_rss = AsyncMock(return_value=full)

    tool = _build_tool(tmp_path, client)
    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(return_value=_make_llm_response('{"ratings": [{"id": "555", "score": 0.5, "reason": "ok"}]}')),
    ):
        result = await tool.execute({"window_minutes": 60})

    assert result.success is True
    client.read_rss.assert_awaited_once_with(555)
    scored = result.data["medium_pending"][0]
    assert scored["link"] == full["metadata"]["link"]
    assert scored["content"] == full["content"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_news_filter_read_rss_failure_skips_article(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    articles = [_make_article(666, "Will fail enrichment")]
    client = AsyncMock()
    client.window_rss = AsyncMock(return_value={"total": 1, "results": articles})
    client.read_rss = AsyncMock(side_effect=OpenAliceError("not found"))

    tool = _build_tool(tmp_path, client)
    with patch(
        "tools.news.news_filter_tool.litellm.acompletion",
        new=AsyncMock(return_value=_make_llm_response('{"score": 0.5, "reason": "ok"}')),
    ):
        result = await tool.execute({"window_minutes": 60})

    assert result.success is True
    assert result.data["new"] == 1
    assert result.data["scored"] == 0
    assert result.data["high"] == []
    assert result.data["medium_pending"] == []


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


@pytest.mark.unit
def test_get_llm_config_returns_global_default():
    from runtime.config_loader import LLMConfig, RuntimeConfig

    cfg = RuntimeConfig(llm=LLMConfig(model="gpt-4o-mini", timeout=30))
    resolved = get_llm_config(cfg, "news_filter_tool")
    assert resolved.model == "gpt-4o-mini"
    assert resolved.timeout == 30


@pytest.mark.unit
def test_get_llm_config_tool_override_merges():
    from runtime.config_loader import LLMConfig, NewsFilterToolConfig, RuntimeConfig

    cfg = RuntimeConfig(
        llm=LLMConfig(model="gpt-4o-mini", timeout=30, api_key="default-key"),
        tools={
            "news_filter_tool": NewsFilterToolConfig(
                llm=LLMConfig(model="anthropic/claude-3-5-sonnet-20241022", timeout=15)
            )
        },
    )
    resolved = get_llm_config(cfg, "news_filter_tool")
    assert resolved.model == "anthropic/claude-3-5-sonnet-20241022"
    assert resolved.timeout == 15
    assert resolved.api_key == "default-key"  # inherited


@pytest.mark.unit
def test_get_llm_config_falls_back_for_tool_without_override():
    from runtime.config_loader import LLMConfig, RuntimeConfig

    cfg = RuntimeConfig(
        llm=LLMConfig(model="gpt-4o-mini"),
        tools={"news_filter_tool": {"llm": {"model": "other-model"}}},
    )
    # Raw dicts are dispatched to the registered model at load time.
    assert get_llm_config(cfg, "news_filter_tool").model == "other-model"
    # Tools without a config entry (or without an `llm` field) get the global default.
    assert get_llm_config(cfg, "unregistered_tool").model == "gpt-4o-mini"


@pytest.mark.unit
def test_tools_block_dispatches_to_registered_model():
    from runtime.config_loader import NewsFilterToolConfig, RuntimeConfig

    cfg = RuntimeConfig(
        tools={"news_filter_tool": {"prompt": {"template": "custom {title}"}}}
    )
    tool_cfg = cfg.tools["news_filter_tool"]
    assert isinstance(tool_cfg, NewsFilterToolConfig)
    assert tool_cfg.prompt.template == "custom {title}"


@pytest.mark.unit
def test_tools_block_unknown_tool_raises():
    from pydantic import ValidationError

    from runtime.config_loader import RuntimeConfig

    with pytest.raises(ValidationError, match="unknown_tool"):
        RuntimeConfig(tools={"unknown_tool": {"llm": {"model": "x"}}})


@pytest.mark.unit
def test_tools_prompt_template_env_override(monkeypatch):
    from runtime.config_loader import RuntimeConfig

    monkeypatch.setenv(
        "QUANT_AGENT_TOOLS__NEWS_FILTER_TOOL__PROMPT__TEMPLATE",
        "env template {title}",
    )
    cfg = RuntimeConfig()
    assert cfg.tools["news_filter_tool"].prompt.template == "env template {title}"


@pytest.mark.unit
def test_get_llm_config_env_override(monkeypatch):
    from runtime.config_loader import RuntimeConfig

    monkeypatch.setenv("QUANT_AGENT_LLM__MODEL", "gpt-4o-mini")
    monkeypatch.setenv(
        "QUANT_AGENT_TOOLS__NEWS_FILTER_TOOL__LLM__MODEL",
        "anthropic/claude-3-5-sonnet-20241022",
    )
    cfg = RuntimeConfig()
    resolved = get_llm_config(cfg, "news_filter_tool")
    assert resolved.model == "anthropic/claude-3-5-sonnet-20241022"
