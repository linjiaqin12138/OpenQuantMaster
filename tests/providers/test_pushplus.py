import json
from unittest.mock import patch

import httpx
import pytest

from src.models.result import AppError, Result
from src.providers.pushplus import send_pushplus, send_pushplus_result

RealAsyncClient = httpx.AsyncClient


def _client_with(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return RealAsyncClient(transport=transport)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_pushplus_posts_the_expected_payload():
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

    with patch("httpx.AsyncClient", lambda **kwargs: _client_with(handler)):
        response = await send_pushplus(
            token="test-token",
            title="Order filled",
            content="BTCUSDT filled",
            template="markdown",
            channel="wechat",
            timeout_seconds=5,
        )

    assert response == {"code": 200, "msg": "ok", "data": "message-1"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_pushplus_raises_provider_error_on_rejection():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 903, "msg": "invalid token"})
    )
    with patch("httpx.AsyncClient", lambda **kwargs: RealAsyncClient(transport=transport)):
        with pytest.raises(AppError) as excinfo:
            await send_pushplus(
                token="test-token",
                title="",
                content="hello",
                template="html",
                channel="wechat",
                timeout_seconds=5,
            )

    assert excinfo.value.code == "provider_rejected"
    assert excinfo.value.message == "invalid token"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_pushplus_result_maps_transport_failure():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=request)

    with patch("httpx.AsyncClient", lambda **kwargs: _client_with(handler)):
        result = await send_pushplus_result(
            token="test-token",
            title="",
            content="hello",
            template="html",
            channel="wechat",
            timeout_seconds=5,
        )

    assert isinstance(result, Result)
    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_pushplus_result_reports_rejection_as_provider_code():
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 903, "msg": "invalid token"})
    )
    with patch("httpx.AsyncClient", lambda **kwargs: RealAsyncClient(transport=transport)):
        result = await send_pushplus_result(
            token="test-token",
            title="",
            content="hello",
            template="html",
            channel="wechat",
            timeout_seconds=5,
        )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_rejected"
