from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest

from runtime.config_loader import OpenAliceConfig
from runtime.openalice_client import OpenAliceClient, OpenAliceError


def _config() -> OpenAliceConfig:
    return OpenAliceConfig(
        workspace_id="ws-test",
        cli_gateway_url="http://alice.test:47332",
        export="data",
        default_timeout=300,
    )


class FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPError(f"HTTP {self.status_code}")


class FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient recording posts."""

    def __init__(self, handler, **kwargs):
        self._handler = handler
        self.kwargs = kwargs
        self.requests: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None):
        self.requests.append(("POST", url, json, headers))
        return self._handler("POST", url, json, headers)


def _patch_httpx(handler):
    holder: dict = {}

    def factory(**kwargs):
        client = FakeAsyncClient(handler, **kwargs)
        holder["client"] = client
        return client

    return patch("runtime.openalice_client.httpx.AsyncClient", new=factory), holder


def _envelope(result: dict) -> FakeResponse:
    return FakeResponse(200, {"content": [{"type": "text", "text": json.dumps(result)}]})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_ask_uses_workspace_export_and_resume_id():
    def handler(method, url, json_body, headers):
        return _envelope({"ok": True, "status": "running", "taskId": "t1", "resumeId": "r1"})

    patcher, holder = _patch_httpx(handler)
    with patcher:
        client = OpenAliceClient(_config())
        result = await client.conversation_ask(
            prompt="hello", timeout_sec=60, resume_id="r0", wait=False
        )

    assert result["ok"] is True
    assert result["resumeId"] == "r1"

    _, url, body, _ = holder["client"].requests[0]
    assert url == "http://alice.test:47332/cli/ws-test/workspace/invoke"
    assert body["tool"] == "conversation_ask"
    assert body["args"]["prompt"] == "hello"
    assert body["args"]["timeoutMs"] == 60000
    assert body["args"]["await"] is False
    assert body["args"]["resumeId"] == "r0"
    assert "wsId" not in body["args"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_ask_without_resume_targets_workspace():
    def handler(method, url, json_body, headers):
        return _envelope({"ok": True, "status": "running", "taskId": "t2", "resumeId": "r-new"})

    patcher, holder = _patch_httpx(handler)
    with patcher:
        client = OpenAliceClient(_config())
        await client.conversation_ask(prompt="fresh", timeout_sec=60, wait=False)

    body = holder["client"].requests[0][2]
    assert body["args"]["wsId"] == "ws-test"
    assert "resumeId" not in body["args"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_ask_wait_extends_http_timeout():
    def handler(method, url, json_body, headers):
        return _envelope({"ok": True, "status": "done", "assistantText": "reply"})

    patcher, holder = _patch_httpx(handler)
    with patcher:
        client = OpenAliceClient(_config())
        result = await client.conversation_ask(prompt="hi", timeout_sec=600, wait=True)

    # await:true blocks server-side up to timeoutMs; HTTP timeout gets headroom.
    assert holder["client"].kwargs["timeout"] == 630.0
    assert result["assistantText"] == "reply"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_ask_nowait_uses_default_timeout():
    def handler(method, url, json_body, headers):
        return _envelope({"ok": True, "status": "running"})

    patcher, holder = _patch_httpx(handler)
    with patcher:
        client = OpenAliceClient(_config(), timeout=30.0)
        await client.conversation_ask(prompt="hi", timeout_sec=600, wait=False)

    assert holder["client"].kwargs["timeout"] == 30.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_conversation_ask_http_400_raises_openalice_error():
    def handler(method, url, json_body, headers):
        return FakeResponse(400, {"error": "Validation failed", "details": "prompt: too long"})

    patcher, _ = _patch_httpx(handler)
    with patcher:
        client = OpenAliceClient(_config())
        with pytest.raises(OpenAliceError, match="gateway request failed"):
            await client.conversation_ask(prompt="hi", timeout_sec=60, wait=False)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_data_export_default_unchanged_for_rss():
    def handler(method, url, json_body, headers):
        return _envelope({"total": 0, "results": []})

    patcher, holder = _patch_httpx(handler)
    with patcher:
        client = OpenAliceClient(_config())
        await client.window_rss(from_time="2026-07-29T00:00:00Z")

    url = holder["client"].requests[0][1]
    assert url == "http://alice.test:47332/cli/ws-test/data/invoke"
