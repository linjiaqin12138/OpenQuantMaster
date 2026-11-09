from typing import Any

import pytest

from src.composition import build_binance_perp_service
from src.config import AppConfig
from src.models.result import Error, Result


def _provider(data: Any):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=True, data=data)

    return _call


def _failing_provider(code: str):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=False, error=Error(code=code, message="exchange failed"))

    return _call


def _app_config(**providers: Any) -> AppConfig:
    return AppConfig.model_validate({"providers": providers})


def _service(**providers: Any):
    return build_binance_perp_service(
        _app_config(binance={"apiKey": "key", "secret": "secret", **providers})
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_balance_returns_the_account_assets(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.binance_perp.fetch_balance_result",
        _provider(
            {
                "assets": {"USDT": {"free": 1000.0, "used": 0.0, "total": 1000.0}},
                "info_keys": [],
            }
        ),
    )

    result = await _service().balance()

    assert result.success is True
    assert result.data["assets"]["USDT"]["total"] == 1000.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_positions_returns_the_open_positions(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.binance_perp.fetch_positions_result",
        _provider([{"symbol": "BTC/USDT:USDT", "side": "long"}]),
    )

    result = await _service().positions({"symbol": "BTC/USDT:USDT"})

    assert result.success is True
    assert result.data["positions"][0]["symbol"] == "BTC/USDT:USDT"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_orders_returns_the_orders(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.binance_perp.fetch_open_orders_result",
        _provider([{"id": "1", "order_kind": "resting"}]),
    )

    result = await _service().open_orders({"symbol": "SUI/USDT:USDT"})

    assert result.success is True
    assert result.data["orders"][0]["id"] == "1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_order_is_previewed_in_dry_run(monkeypatch):
    def _unexpected_call(**kwargs: Any) -> Result:
        raise AssertionError("the exchange must not be called in dry-run")

    monkeypatch.setattr(
        "src.use_cases.binance_perp.create_order_result",
        _unexpected_call,
    )

    result = await _service().create_order(
        {
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
        }
    )

    assert result.success is True
    assert result.data["dry_run"] is True
    assert result.data["planned"]["order_type"] == "market"
    assert result.data["order"] is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_order_is_previewed_in_dry_run(monkeypatch):
    def _unexpected_call(**kwargs: Any) -> Result:
        raise AssertionError("the exchange must not be called in dry-run")

    monkeypatch.setattr(
        "src.use_cases.binance_perp.cancel_order_result",
        _unexpected_call,
    )

    result = await _service().cancel_order(
        {"order_id": "12345", "symbol": "BTC/USDT:USDT"}
    )

    assert result.data["dry_run"] is True
    assert result.data["planned"]["order_id"] == "12345"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_leverage_is_previewed_in_dry_run(monkeypatch):
    def _unexpected_call(**kwargs: Any) -> Result:
        raise AssertionError("the exchange must not be called in dry-run")

    monkeypatch.setattr(
        "src.use_cases.binance_perp.set_leverage_result",
        _unexpected_call,
    )

    result = await _service().set_leverage({"leverage": 5, "symbol": "BTC/USDT:USDT"})

    assert result.data["dry_run"] is True
    assert result.data["planned"]["leverage"] == 5


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_position_mode_is_previewed_in_dry_run(monkeypatch):
    def _unexpected_call(**kwargs: Any) -> Result:
        raise AssertionError("the exchange must not be called in dry-run")

    monkeypatch.setattr(
        "src.use_cases.binance_perp.set_position_mode_result",
        _unexpected_call,
    )

    result = await _service().set_position_mode({"hedge": True})

    assert result.data["dry_run"] is True
    assert result.data["planned"]["hedge"] is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_order_reaches_the_exchange_when_not_dry_run(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data={"id": "1", "status": "closed"})

    monkeypatch.setattr("src.use_cases.binance_perp.create_order_result", _call)

    result = await _service().create_order(
        {
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
            "dry_run": False,
        }
    )

    assert captured["symbol"] == "BTC/USDT:USDT"
    assert captured["side"] == "buy"
    assert result.success is True
    assert result.data["dry_run"] is False
    assert result.data["order"]["id"] == "1"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_order_validates_the_request():
    result = await _service().create_order(
        {
            "symbol": "BTC/USDT:USDT",
            "side": "sell",
            "order_type": "stop_market",
            "amount": 0.001,
        }
    )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "invalid_input"
    assert "stop_price" in result.error.message


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_exchange_outage_is_mapped(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.binance_perp.fetch_balance_result",
        _failing_provider("provider_unavailable"),
    )

    result = await _service().balance()

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "exchange_unavailable"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_an_exchange_rejection_is_mapped(monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.binance_perp.create_order_result",
        _failing_provider("provider_rejected"),
    )

    result = await _service().create_order(
        {
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
            "dry_run": False,
        }
    )

    assert result.error is not None
    assert result.error.code == "order_rejected"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_the_external_configuration_reaches_the_exchange(monkeypatch):
    captured: dict[str, Any] = {}

    async def _call(**kwargs: Any) -> Result:
        captured.update(kwargs)
        return Result(success=True, data={"assets": {}, "info_keys": []})

    monkeypatch.setattr("src.use_cases.binance_perp.fetch_balance_result", _call)

    service = build_binance_perp_service(
        _app_config(binance={"apiKey": "key", "secret": "secret", "sandbox": True})
    )
    await service.balance()

    assert captured["venue"].api_key == "key"
    assert captured["venue"].secret == "secret"
    assert captured["venue"].sandbox is True
    assert captured["venue"].product == "usdm"
