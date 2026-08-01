from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from runtime.openalice_client import OpenAliceClient, OpenAliceError
from tools.agent.openalice_tool import OpenAliceTool

WORKSPACE_ID = "auto-quant-clear-willow-field"  # default when no config.yaml is present


def _ask_result(**overrides):
    result = {
        "ok": True,
        "status": "done",
        "taskId": "task-1",
        "resumeId": "resume-1",
        "assistantText": "analysis complete",
        "durationMs": 100,
    }
    result.update(overrides)
    return result


def _build_tool(tmp_path: Path, client: AsyncMock) -> OpenAliceTool:
    return OpenAliceTool(openalice_client=client, session_path=tmp_path / "openalice_session.json")


def _read_session(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.unit
@pytest.mark.asyncio
async def test_happy_path_persists_resume_id(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(return_value=_ask_result())
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "analyze BTC"})

    assert result.success is True
    assert result.data["response"] == "analysis complete"
    assert result.data["session_id"] == "resume-1"
    assert result.data["task_id"] == "task-1"
    assert result.data["status"] == "done"
    assert result.data["truncated"] is False

    client.conversation_ask.assert_awaited_once()
    kwargs = client.conversation_ask.await_args.kwargs
    assert kwargs["prompt"] == "analyze BTC"
    assert kwargs["resume_id"] is None
    assert kwargs["wait"] is True

    session = _read_session(tmp_path / "openalice_session.json")
    assert session[WORKSPACE_ID]["resume_id"] == "resume-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_reuses_stored_resume_id(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_path = tmp_path / "openalice_session.json"
    session_path.write_text(
        json.dumps({WORKSPACE_ID: {"resume_id": "old-resume", "updated_at": "2026-07-29T00:00:00Z"}}),
        encoding="utf-8",
    )
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(return_value=_ask_result())
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "continue"})

    assert result.success is True
    assert client.conversation_ask.await_args.kwargs["resume_id"] == "old-resume"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_resume_false_ignores_stored_resume_id(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_path = tmp_path / "openalice_session.json"
    session_path.write_text(
        json.dumps({WORKSPACE_ID: {"resume_id": "old-resume", "updated_at": "x"}}),
        encoding="utf-8",
    )
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(return_value=_ask_result())
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "fresh", "resume": False})

    assert result.success is True
    assert client.conversation_ask.await_args.kwargs["resume_id"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_unavailable_resume_retries_fresh_and_updates_session(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_path = tmp_path / "openalice_session.json"
    session_path.write_text(
        json.dumps({WORKSPACE_ID: {"resume_id": "stale", "updated_at": "x"}}),
        encoding="utf-8",
    )
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(
        side_effect=[
            {"ok": False, "status": "unavailable",
             "resolution": {"mode": "unavailable", "reason": "missing-session"}},
            _ask_result(resumeId="new-resume"),
        ]
    )
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "retry me"})

    assert result.success is True
    assert client.conversation_ask.await_count == 2
    first, second = client.conversation_ask.await_args_list
    assert first.kwargs["resume_id"] == "stale"
    assert second.kwargs["resume_id"] is None
    assert result.data["session_id"] == "new-resume"
    session = _read_session(session_path)
    assert session[WORKSPACE_ID]["resume_id"] == "new-resume"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_also_fails_returns_failure(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(
        side_effect=[
            {"ok": False, "status": "unavailable",
             "resolution": {"mode": "unavailable", "reason": "retired-session"}},
            {"ok": False, "error": "capacity"},
        ]
    )
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "doom"})

    assert result.success is False
    assert "capacity" in result.error
    assert client.conversation_ask.await_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_failed_task_status_returns_failure(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(
        return_value=_ask_result(status="failed", error="agent crashed", assistantText=None)
    )
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "boom"})

    assert result.success is False
    assert "agent crashed" in result.error
    assert not (tmp_path / "openalice_session.json").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_not_ok_result_returns_failure_without_touching_session(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(return_value={"ok": False, "error": "capacity"})
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "boom"})

    assert result.success is False
    assert "capacity" in result.error
    assert not (tmp_path / "openalice_session.json").exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_gateway_error_returns_failure(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(side_effect=OpenAliceError("connection refused"))
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "boom"})

    assert result.success is False
    assert "connection refused" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_prompt_truncated_to_16000_chars(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(return_value=_ask_result())
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "x" * 17000})

    assert result.success is True
    assert result.data["truncated"] is True
    assert len(client.conversation_ask.await_args.kwargs["prompt"]) == 16000


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_false_returns_running_status(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(
        return_value=_ask_result(status="running", assistantText=None)
    )
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "fire and forget", "wait": False})

    assert result.success is True
    assert result.data["status"] == "running"
    assert result.data["response"] == ""
    assert client.conversation_ask.await_args.kwargs["wait"] is False
    # resumeId is still persisted so the next turn can continue the session
    session = _read_session(tmp_path / "openalice_session.json")
    assert session[WORKSPACE_ID]["resume_id"] == "resume-1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_corrupt_session_file_treated_as_empty(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    session_path = tmp_path / "openalice_session.json"
    session_path.write_text("{not json", encoding="utf-8")
    client = AsyncMock(spec=OpenAliceClient)
    client.conversation_ask = AsyncMock(return_value=_ask_result())
    tool = _build_tool(tmp_path, client)

    result = await tool.execute({"prompt": "hello"})

    assert result.success is True
    assert client.conversation_ask.await_args.kwargs["resume_id"] is None
