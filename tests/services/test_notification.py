import json
from unittest.mock import patch

import httpx
import pytest

from src.config import NotificationConfig, PushPlusProviderConfig
from src.services.notification import NotificationService

RealAsyncClient = httpx.AsyncClient


def service() -> NotificationService:
    return NotificationService(
        NotificationConfig(pushplus=PushPlusProviderConfig(token="test-token"))
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notification_sends_pushplus_message():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://www.pushplus.plus/send"
        assert json.loads(request.content) == {
            "token": "test-token",
            "title": "Order filled",
            "content": "BTCUSDT filled",
            "template": "markdown",
            "channel": "wechat",
        }
        return httpx.Response(200, json={"code": 200, "msg": "ok", "data": "message-1"})

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", lambda **kwargs: RealAsyncClient(transport=transport)):
        result = await service().run(
            {"title": "Order filled", "content": "BTCUSDT filled", "format": "markdown"}
        )

    assert result.success is True
    assert result.data == {
        "provider": "pushplus",
        "format": "markdown",
        "message_id": "message-1",
        "response": {"code": 200, "msg": "ok", "data": "message-1"},
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notification_uses_default_provider_and_format():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["template"] == "html"
        return httpx.Response(200, json={"code": 200, "msg": "ok", "data": None})

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", lambda **kwargs: RealAsyncClient(transport=transport)):
        result = await service().run({"content": "hello"})

    assert result.success is True
    assert result.data["provider"] == "pushplus"
    assert result.data["format"] == "html"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notification_reports_provider_rejection():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 903, "msg": "invalid token"})
    )
    with patch("httpx.AsyncClient", lambda **kwargs: RealAsyncClient(transport=transport)):
        result = await service().run({"content": "hello"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_rejected"
    assert result.error.message == "invalid token"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notification_reports_transport_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    transport = httpx.MockTransport(handler)
    with patch("httpx.AsyncClient", lambda **kwargs: RealAsyncClient(transport=transport)):
        result = await service().run({"content": "hello"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_request_failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_notification_requires_token():
    result = await NotificationService(NotificationConfig()).run({"content": "hello"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "missing_provider_token"


@pytest.mark.unit
@pytest.mark.asyncio
@pytest.mark.parametrize("inputs", [{"title": "missing content"}, {"content": ""}, {"content": "x", "format": "xml"}])
async def test_notification_validates_input(inputs):
    result = await service().run(inputs)

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "unhandled_exception"
