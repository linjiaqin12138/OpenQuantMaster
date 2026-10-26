import json
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from runtime.cli import cli


def _write_config(tmp_path) -> None:
    (tmp_path / "config.yaml").write_text(
        """
app_name: OpenQuantMaster
environment: testing
exchanges:
  binance:
    apiKey: test-key
    secret: test-secret
    usdm:
      ccxt_id: binanceusdm
      sandbox: true
execution:
  binance_perp:
    exchange: binance
    product: usdm
"""
    )


class FakeExchange:
    """Stand-in for ccxt.async_support.binanceusdm (side-effect SDK only)."""

    instances: list["FakeExchange"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.kwargs = kwargs
        type(self).instances.append(self)
        self.fetch_balance = AsyncMock(
            return_value={
                "free": {"USDT": 1000.0},
                "used": {"USDT": 0.0},
                "total": {"USDT": 1000.0},
                "info": {},
            }
        )
        self.fetch_positions = AsyncMock(return_value=[])
        self.fetch_open_orders = AsyncMock(return_value=[])
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


def _invoke_tool(inputs: dict) -> tuple[int, dict]:
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "tool",
            "binance_perp_tool",
            "--inputs",
            json.dumps(inputs),
        ],
    )
    payload = json.loads(result.output) if result.output.strip() else {}
    return result.exit_code, payload


@pytest.fixture
def ccxt_fake(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    FakeExchange.instances = []
    fake_ccxt = type("ccxt", (), {"binanceusdm": FakeExchange})()
    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt}):
        yield FakeExchange


@pytest.mark.unit
def test_cli_lists_binance_perp_tool(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)
    result = CliRunner().invoke(cli, ["list-tools"])
    assert result.exit_code == 0
    rows = json.loads(result.output)
    names = {row["name"] for row in rows}
    assert "binance_perp_tool" in names


@pytest.mark.unit
def test_balance_via_cli(ccxt_fake):
    exit_code, payload = _invoke_tool({"action": "balance"})
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["data"]["action"] == "balance"
    assert payload["data"]["ccxt_id"] == "binanceusdm"
    assert payload["data"]["sandbox"] is True
    assert payload["data"]["result"]["assets"]["USDT"]["total"] == 1000.0
    assert len(ccxt_fake.instances) == 1
    ccxt_fake.instances[0].fetch_balance.assert_awaited_once()
    ccxt_fake.instances[0].close.assert_awaited_once()


@pytest.mark.unit
def test_create_order_dry_run_skips_sdk_write(ccxt_fake):
    exit_code, payload = _invoke_tool(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
        }
    )
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["planned"]["order_type"] == "market"
    assert ccxt_fake.instances == []


@pytest.mark.unit
def test_create_order_live_calls_sdk(ccxt_fake):
    exit_code, payload = _invoke_tool(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "buy",
            "order_type": "market",
            "amount": 0.001,
            "dry_run": False,
        }
    )
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["data"]["dry_run"] is False
    assert payload["data"]["result"]["id"] == "1"
    assert len(ccxt_fake.instances) == 1
    exchange = ccxt_fake.instances[0]
    exchange.create_order.assert_awaited_once()
    exchange.set_sandbox_mode.assert_awaited_once_with(True)
    exchange.close.assert_awaited_once()


@pytest.mark.unit
def test_stop_market_requires_stop_price_via_cli(ccxt_fake):
    exit_code, payload = _invoke_tool(
        {
            "action": "create_order",
            "symbol": "BTC/USDT:USDT",
            "side": "sell",
            "order_type": "stop_market",
            "amount": 0.001,
        }
    )
    assert exit_code == 0
    assert payload["success"] is False
    assert "stop_price" in (payload.get("error") or "")
    assert ccxt_fake.instances == []


@pytest.mark.unit
def test_stop_market_dry_run_planned_via_cli(ccxt_fake):
    exit_code, payload = _invoke_tool(
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
    assert exit_code == 0
    assert payload["success"] is True
    planned = payload["data"]["planned"]
    assert planned["order_type"] == "stop_market"
    assert planned["stop_price"] == 45000.0
    assert planned["position_side"] == "LONG"
    assert ccxt_fake.instances == []


@pytest.mark.unit
def test_set_position_mode_dry_run_via_cli(ccxt_fake):
    exit_code, payload = _invoke_tool({"action": "set_position_mode", "hedge": True})
    assert exit_code == 0
    assert payload["success"] is True
    assert payload["data"]["planned"]["hedge"] is True
    assert ccxt_fake.instances == []
