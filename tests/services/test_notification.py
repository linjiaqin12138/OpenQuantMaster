from typing import Any

import pytest

from src.composition import build_notification_service
from src.config import AppConfig
from src.models.result import Error, Result


def _provider(response: dict[str, Any]):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=True, data=response)

    return _call


def _failing_provider(code: str):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=False, error=Error(code=code, message="provider failed"))

    return _call


def _app_config(**providers: Any) -> AppConfig:
    return AppConfig.model_validate({"providers": providers})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_delivers_the_notification(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.notification.send_pushplus_result",
        _provider({"code": 200, "msg": "ok", "data": "message-1"}),
    )

    service = build_notification_service(
        _app_config(pushplus={"token": "pushplus-token"})
    )
    result = await service.send(
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
async def test_send_maps_a_provider_rejection(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.notification.send_pushplus_result",
        _failing_provider("provider_rejected"),
    )

    service = build_notification_service(
        _app_config(pushplus={"token": "pushplus-token"})
    )
    result = await service.send({"content": "hello"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "notification_rejected"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_maps_a_provider_outage(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.notification.send_pushplus_result",
        _failing_provider("provider_timeout"),
    )

    service = build_notification_service(
        _app_config(pushplus={"token": "pushplus-token"})
    )
    result = await service.send({"content": "hello"})

    assert result.error is not None
    assert result.error.code == "notification_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_maps_an_unknown_provider_failure(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.notification.send_pushplus_result",
        _failing_provider("unknown"),
    )

    service = build_notification_service(
        _app_config(pushplus={"token": "pushplus-token"})
    )
    result = await service.send({"content": "hello"})

    assert result.error is not None
    assert result.error.code == "notification_failed"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_requires_a_provider_token():
    service = build_notification_service(_app_config())

    result = await service.send({"content": "hello"})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "missing_provider_token"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_send_validates_the_request():
    service = build_notification_service(
        _app_config(pushplus={"token": "pushplus-token"})
    )

    result = await service.send({"content": ""})

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_input"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_external_configuration_reaches_the_provider(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data={"code": 200, "data": "message-1"})

    monkeypatch.setattr("src.use_cases.notification.send_pushplus_result", _call)

    service = build_notification_service(
        _app_config(pushplus={"token": "pushplus-token", "channel": "wechat", "timeout": 5})
    )
    await service.send({"content": "hello"})

    assert captured["token"] == "pushplus-token"
    assert captured["channel"] == "wechat"
    assert captured["timeout_seconds"] == 5
