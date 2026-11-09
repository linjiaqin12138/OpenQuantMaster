from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.providers.ccxt import (
    CcxtVenue,
    fetch_balance,
    fetch_crypto_ohlcv,
    fetch_crypto_ohlcv_result,
    fetch_crypto_ticker,
    fetch_open_orders,
)


class FakeExchange:
    """Stand-in for ccxt.async_support.binanceusdm (side-effect SDK only)."""

    instances: list["FakeExchange"] = []
    resting_orders: list[dict] = []
    conditional_orders: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).instances.append(self)
        self.fetch_ohlcv = AsyncMock(
            return_value=[[1_700_000_000_000, 100.0, 110.0, 90.0, 105.0, 1000.0]]
        )
        self.fetch_ticker = AsyncMock(
            return_value={
                "symbol": "BTC/USDT:USDT",
                "timestamp": 1_700_000_000_000,
                "datetime": "2023-11-14T22:13:20.000Z",
                "last": 105.0,
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "previousClose": 99.0,
                "change": 6.0,
                "percentage": 6.06,
                "bid": 104.9,
                "ask": 105.1,
                "info": {},
            }
        )
        self.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 1000.0, "EMPTY": 0.0},
                "used": {"USDT": 0.0, "EMPTY": 0.0},
                "total": {"USDT": 1000.0, "EMPTY": 0.0},
                "info": {"a": 1},
            }
        )
        self.fetch_open_orders = AsyncMock(side_effect=self._fetch_open_orders)
        self.close = AsyncMock()
        self.set_sandbox_mode = MagicMock()

    async def _fetch_open_orders(self, symbol=None, since=None, limit=None, params=None):
        params = params or {}
        if params.get("stop") or params.get("trigger"):
            return list(type(self).conditional_orders)
        return list(type(self).resting_orders)


@pytest.fixture
def ccxt_fake():
    FakeExchange.instances = []
    FakeExchange.resting_orders = []
    FakeExchange.conditional_orders = []
    fake_ccxt = type("ccxt", (), {"binanceusdm": FakeExchange, "binance": FakeExchange})()
    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt}):
        yield FakeExchange


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_crypto_ohlcv_normalizes_rows(ccxt_fake):
    venue = CcxtVenue(exchange="binance", product="usdm", sandbox=True)

    bars = await fetch_crypto_ohlcv(
        venue=venue,
        symbol="BTC/USDT:USDT",
        interval="1h",
        limit=1,
    )

    assert bars == [
        {
            "timestamp": "2023-11-14T22:13:20Z",
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "close": 105.0,
            "volume": 1000.0,
        }
    ]
    assert ccxt_fake.instances[0].set_sandbox_mode.called is True
    assert ccxt_fake.instances[0].close.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_crypto_ticker_normalizes_the_snapshot(ccxt_fake):
    ticker = await fetch_crypto_ticker(
        venue=CcxtVenue(exchange="binance", product="usdm"),
        symbol="BTC/USDT:USDT",
    )

    assert ticker["name"] == "BTC/USDT:USDT"
    assert ticker["price"] == 105.0
    assert ticker["previous_close"] == 99.0
    assert ticker["change"] == 6.0
    assert ticker["change_percent"] == 6.06
    assert ticker["bid"] == 104.9
    assert ticker["ask"] == 105.1
    assert ticker["quote_time"] == "2023-11-14T22:13:20Z"
    assert ccxt_fake.instances[0].close.await_count == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_balance_keeps_non_zero_assets_only(ccxt_fake):
    venue = CcxtVenue(exchange="binance", product="usdm")

    balance = await fetch_balance(venue=venue)

    assert balance["assets"] == {
        "USDT": {"free": 1000.0, "used": 0.0, "total": 1000.0}
    }
    assert balance["info_keys"] == ["a"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_fetch_open_orders_merges_conditional_orders(ccxt_fake):
    FakeExchange.resting_orders = [
        {
            "id": "99",
            "symbol": "SUI/USDT:USDT",
            "type": "limit",
            "side": "sell",
            "price": 0.9,
            "amount": 10.0,
            "filled": 0.0,
            "remaining": 10.0,
            "status": "open",
            "info": {},
        }
    ]
    FakeExchange.conditional_orders = [
        {
            "id": "1000002667807070",
            "symbol": "SUI/USDT:USDT",
            "type": "market",
            "side": "buy",
            "amount": 48.3,
            "filled": 0.0,
            "remaining": 48.3,
            "status": "open",
            "stopPrice": 0.8488,
            "info": {
                "algoId": 1000002667807070,
                "algoType": "CONDITIONAL",
                "orderType": "TAKE_PROFIT_MARKET",
                "workingType": "CONTRACT_PRICE",
                "algoStatus": "NEW",
                "closePosition": False,
            },
        }
    ]

    orders = await fetch_open_orders(
        venue=CcxtVenue(exchange="binance", product="usdm"),
        symbol="SUI/USDT:USDT",
    )

    assert [order["order_kind"] for order in orders] == ["resting", "conditional"]
    assert orders[1]["type"] == "take_profit_market"
    assert orders[1]["stopPrice"] == 0.8488
    assert orders[1]["workingType"] == "CONTRACT_PRICE"
    assert orders[1]["algoStatus"] == "NEW"
    assert orders[1]["closePosition"] is False


@pytest.mark.unit
@pytest.mark.asyncio
async def test_exchange_failures_are_mapped_to_provider_error_codes():
    import ccxt

    class FailingExchange:
        def __init__(self, *args, **kwargs) -> None:
            self.fetch_ohlcv = AsyncMock(side_effect=ccxt.NetworkError("no route"))
            self.close = AsyncMock()

    fake_ccxt = type("ccxt", (), {"binanceusdm": FailingExchange})()
    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt}):
        result = await fetch_crypto_ohlcv_result(
            venue=CcxtVenue(exchange="binance", product="usdm"),
            symbol="BTC/USDT:USDT",
            interval="1h",
            limit=1,
        )

    assert result.success is False
    assert result.error is not None
    assert result.error.code == "provider_unavailable"
