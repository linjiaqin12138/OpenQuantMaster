from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from runtime.config_loader import NotifierConfig, PushplusConfig, TelegramConfig, EmailConfig
from runtime.notifier.composite import CompositeNotifier
from runtime.notifier.email_notifier import EmailNotifier
from runtime.notifier.pushplus_notifier import PushplusNotifier
from runtime.notifier.telegram_notifier import TelegramNotifier


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pushplus_notifier_sends_correct_payload():
    config = PushplusConfig(enabled=True, token="test-token")
    notifier = PushplusNotifier(config)

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.raise_for_status.return_value = None

    async_mock_client = AsyncMock(spec=httpx.AsyncClient)
    async_mock_client.__aenter__ = AsyncMock(return_value=async_mock_client)
    async_mock_client.__aexit__ = AsyncMock(return_value=None)
    async_mock_client.post.return_value = mock_response

    captured_payload: dict[str, Any] | None = None

    def capture_post(url, *, json=None, **kwargs):
        nonlocal captured_payload
        captured_payload = json
        return mock_response

    async_mock_client.post.side_effect = capture_post

    with patch("runtime.notifier.pushplus_notifier.httpx.AsyncClient", return_value=async_mock_client):
        result = await notifier.send("Test Subject", "Test Body")

    assert result == {"pushplus": "ok"}
    assert captured_payload is not None
    assert captured_payload["token"] == "test-token"
    assert captured_payload["title"] == "Test Subject"
    assert captured_payload["content"] == "Test Body"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pushplus_notifier_missing_token():
    config = PushplusConfig(enabled=True, token="")
    notifier = PushplusNotifier(config)
    result = await notifier.send("Subject", "Body")

    assert result["pushplus"] == "missing token"
    assert result["success"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_pushplus_notifier_http_error():
    config = PushplusConfig(enabled=True, token="test-token")
    notifier = PushplusNotifier(config)

    async_mock_client = AsyncMock(spec=httpx.AsyncClient)
    async_mock_client.__aenter__ = AsyncMock(return_value=async_mock_client)
    async_mock_client.__aexit__ = AsyncMock(return_value=None)
    async_mock_client.post.side_effect = httpx.ConnectError("No network")

    with patch("runtime.notifier.pushplus_notifier.httpx.AsyncClient", return_value=async_mock_client):
        result = await notifier.send("Subject", "Body")

    assert result["success"] is False
    assert "error" in result["pushplus"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_telegram_notifier_not_implemented():
    config = TelegramConfig(enabled=True)
    notifier = TelegramNotifier(config)
    result = await notifier.send("Subject", "Body")
    assert result == {"telegram": "not_implemented"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_email_notifier_not_implemented():
    config = EmailConfig(enabled=True)
    notifier = EmailNotifier(config)
    result = await notifier.send("Subject", "Body")
    assert result == {"email": "not_implemented"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_composite_notifier_only_sends_to_enabled_channels():
    config = NotifierConfig(
        pushplus=PushplusConfig(enabled=True, token="token"),
        telegram=TelegramConfig(enabled=True),
        email=EmailConfig(enabled=False),
    )
    notifier = CompositeNotifier(config)

    result = await notifier.send("Subject", "Body")

    assert "pushplus" in result
    assert "telegram" in result
    assert "email" not in result
