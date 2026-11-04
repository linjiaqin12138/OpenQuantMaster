from unittest.mock import AsyncMock, patch

import pytest

from runtime.services.binance_perp import BinancePerp, BinancePerpConfig


class FakeExchange:
    """Stand-in for ccxt.async_support.binanceusdm (side-effect SDK only)."""

    instances: list["FakeExchange"] = []
    resting_orders: list[dict] = []
    conditional_orders: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).instances.append(self)
        self._resting_orders = list(type(self).resting_orders)
        self._conditional_orders = list(type(self).conditional_orders)
        self.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 1000.0},
                "used": {"USDT": 0.0},
                "total": {"USDT": 1000.0},
                "info": {},
            }
        )
        self.fetch_positions = AsyncMock(return_value=[])
        self.fetch_open_orders = AsyncMock(side_effect=self._fetch_open_orders)
        self.create_order = AsyncMock(
            return_value={
                "id": "1",
                "symbol": "BTC/USDT:USDT",
                "type": "market",
                "side": "buy",
                "amount": 0.001,
                "status": "closed",
            }
        )
        self.cancel_order = AsyncMock(return_value={"id": "1", "status": "canceled"})
        self.set_leverage = AsyncMock(return_value={"leverage": 5})
        self.set_margin_mode = AsyncMock(return_value={"marginMode": "isolated"})
        self.set_position_mode = AsyncMock(return_value={"dualSidePosition": True})
        self.close = AsyncMock()
        self.set_sandbox_mode = AsyncMock()

    async def _fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        params = params or {}
        if params.get("stop") or params.get("trigger"):
            return list(self._conditional_orders)
        return list(self._resting_orders)


@pytest.fixture
def ccxt_fake():
    FakeExchange.instances = []
    FakeExchange.resting_orders = []
    FakeExchange.conditional_orders = []
    fake_ccxt = type("ccxt", (), {"binanceusdm": FakeExchange})()
    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt}):
        yield FakeExchange


def _service() -> BinancePerp:
    return BinancePerp(
        BinancePerpConfig(
            exchange="binance",
            product="usdm",
            sandbox=True,
            api_key="test-key",
            secret="test-secret",
        )
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_balance(ccxt_fake):
    result = await _service().run({"action": "balance"})
    assert result.success is True
    assert result.data["action"] == "balance"
    assert result.data["exchange"] == "binance"
    assert result.data["product"] == "usdm"
    assert result.data["sandbox"] is True
    assert result.data["result"]["assets"]["USDT"]["total"] == 1000.0
    assert len(ccxt_fake.instances) == 1
    ccxt_fake.instances[0].fetch_balance.assert_awaited_once()
    ccxt_fake.instances[0].close.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_order_dry_run_skips_sdk_write(ccxt_fake):
    result = await _service().run(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
        }
    )
    assert result.success is True
    assert result.data["dry_run"] is True
    assert result.data["planned"]["order_type"] == "market"
    assert ccxt_fake.instances == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_order_live_calls_sdk(ccxt_fake):
    result = await _service().run(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
            "dry_run": False,
        }
    )
    assert result.success is True
    assert result.data["dry_run"] is False
    assert result.data["result"]["id"] == "1"
    assert len(ccxt_fake.instances) == 1
    exchange = ccxt_fake.instances[0]
    exchange.create_order.assert_awaited_once()
    exchange.set_sandbox_mode.assert_awaited_once_with(True)
    exchange.close.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stop_market_requires_stop_price(ccxt_fake):
    result = await _service().run(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "sell",
            "order_type": "stop_market",
            "amount": 0.001,
        }
    )
    assert result.success is False
    assert "stop_price" in (result.error or "")
    assert ccxt_fake.instances == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stop_market_dry_run_planned(ccxt_fake):
    result = await _service().run(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "sell",
            "order_type": "stop_market",
            "amount": 0.001,
            "stop_price": 45000.0,
            "reduce_only": True,
            "position_side": "LONG",
        }
    )
    assert result.success is True
    planned = result.data["planned"]
    assert planned["order_type"] == "stop_market"
    assert planned["stop_price"] == 45000.0
    assert planned["position_side"] == "LONG"
    assert ccxt_fake.instances == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_set_position_mode_dry_run(ccxt_fake):
    result = await _service().run({"action": "set_position_mode", "hedge": True})
    assert result.success is True
    assert result.data["planned"]["hedge"] is True
    assert ccxt_fake.instances == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_orders_includes_conditional_by_default(ccxt_fake):
    FakeExchange.resting_orders = [
        {
            "id": "99",
            "clientOrderId": "limit-1",
            "symbol": "SUI/USDT:USDT",
            "type": "limit",
            "side": "sell",
            "price": 0.9,
            "amount": 10.0,
            "filled": 0.0,
            "remaining": 10.0,
            "status": "open",
            "reduceOnly": False,
            "stopPrice": None,
            "timestamp": 1,
            "info": {},
        }
    ]
    FakeExchange.conditional_orders = [
        {
            "id": "1000002667807070",
            "clientOrderId": "stToAg_OTOCO_1",
            "symbol": "SUI/USDT:USDT",
            "type": "market",
            "side": "buy",
            "price": None,
            "amount": 48.3,
            "filled": 0.0,
            "remaining": 48.3,
            "status": "open",
            "reduceOnly": True,
            "stopPrice": 0.8488,
            "triggerPrice": 0.8488,
            "timestamp": 2,
            "info": {
                "algoId": 1000002667807070,
                "algoType": "CONDITIONAL",
                "orderType": "TAKE_PROFIT_MARKET",
                "workingType": "CONTRACT_PRICE",
                "algoStatus": "NEW",
                "closePosition": False,
            },
        },
        {
            "id": "1000002667807071",
            "clientOrderId": "stToAg_OTOCO_2",
            "symbol": "SUI/USDT:USDT",
            "type": "market",
            "side": "buy",
            "price": None,
            "amount": 48.3,
            "filled": 0.0,
            "remaining": 48.3,
            "status": "open",
            "reduceOnly": True,
            "stopPrice": 0.9008,
            "triggerPrice": 0.9008,
            "timestamp": 3,
            "info": {
                "algoId": 1000002667807071,
                "algoType": "CONDITIONAL",
                "orderType": "STOP_MARKET",
                "workingType": "CONTRACT_PRICE",
                "algoStatus": "NEW",
                "closePosition": False,
            },
        },
    ]

    result = await _service().run({"action": "open_orders", "symbol": "SUI/USDT:USDT"})

    assert result.success is True
    rows = result.data["result"]
    assert len(rows) == 3
    assert rows[0]["order_kind"] == "resting"
    assert rows[0]["type"] == "limit"
    assert rows[1]["order_kind"] == "conditional"
    assert rows[1]["type"] == "take_profit_market"
    assert rows[1]["stopPrice"] == 0.8488
    assert rows[1]["workingType"] == "CONTRACT_PRICE"
    assert rows[1]["algoStatus"] == "NEW"
    assert rows[1]["closePosition"] is False
    assert rows[2]["order_kind"] == "conditional"
    assert rows[2]["type"] == "stop_market"
    assert rows[2]["stopPrice"] == 0.9008

    exchange = ccxt_fake.instances[0]
    assert exchange.fetch_open_orders.await_count == 2
    exchange.fetch_open_orders.assert_any_await("SUI/USDT:USDT")
    exchange.fetch_open_orders.assert_any_await(
        "SUI/USDT:USDT", params={"stop": True}
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_open_orders_can_skip_conditional(ccxt_fake):
    FakeExchange.resting_orders = [
        {
            "id": "99",
            "clientOrderId": "limit-1",
            "symbol": "SUI/USDT:USDT",
            "type": "limit",
            "side": "sell",
            "price": 0.9,
            "amount": 10.0,
            "filled": 0.0,
            "remaining": 10.0,
            "status": "open",
            "reduceOnly": False,
            "stopPrice": None,
            "timestamp": 1,
            "info": {},
        }
    ]
    FakeExchange.conditional_orders = [
        {
            "id": "1001",
            "clientOrderId": "tp-1",
            "symbol": "SUI/USDT:USDT",
            "type": "market",
            "side": "buy",
            "amount": 1.0,
            "filled": 0.0,
            "remaining": 1.0,
            "status": "open",
            "reduceOnly": True,
            "stopPrice": 0.8,
            "timestamp": 2,
            "info": {"algoType": "CONDITIONAL", "orderType": "TAKE_PROFIT_MARKET"},
        }
    ]

    result = await _service().run(
        {
            "action": "open_orders",
            "symbol": "SUI/USDT:USDT",
            "include_conditional": False,
        }
    )

    assert result.success is True
    rows = result.data["result"]
    assert len(rows) == 1
    assert rows[0]["order_kind"] == "resting"
    assert ccxt_fake.instances[0].fetch_open_orders.await_count == 1
