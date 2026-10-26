from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field, model_validator

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ToolResult

Action = Literal[
    "balance",
    "positions",
    "open_orders",
    "create_order",
    "cancel_order",
    "set_leverage",
    "set_margin_mode",
    "set_position_mode",
]

OrderType = Literal[
    "market",
    "limit",
    "stop_market",
    "take_profit_market",
    "stop",
    "take_profit",
    "trailing_stop_market",
]

WRITE_ACTIONS: frozenset[str] = frozenset(
    {
        "create_order",
        "cancel_order",
        "set_leverage",
        "set_margin_mode",
        "set_position_mode",
    }
)

CONDITIONAL_STOP_TYPES: frozenset[str] = frozenset(
    {
        "stop_market",
        "take_profit_market",
        "stop",
        "take_profit",
    }
)


class BinancePerpInput(BaseModel):
    action: Action
    dry_run: bool = True
    symbol: str | None = None
    side: Literal["buy", "sell"] | None = None
    order_type: OrderType | None = None
    amount: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    callback_rate: float | None = Field(default=None, ge=0.1, le=10)
    activation_price: float | None = Field(default=None, gt=0)
    order_id: str | None = None
    leverage: int | None = Field(default=None, ge=1, le=125)
    margin_mode: Literal["isolated", "cross"] | None = None
    reduce_only: bool = False
    close_position: bool = False
    position_side: Literal["BOTH", "LONG", "SHORT"] | None = None
    working_type: Literal["CONTRACT_PRICE", "MARK_PRICE"] | None = None
    hedge: bool | None = None

    @model_validator(mode="after")
    def validate_action_params(self) -> BinancePerpInput:
        action = self.action
        if action == "create_order":
            missing = [
                name
                for name, value in (
                    ("symbol", self.symbol),
                    ("side", self.side),
                    ("order_type", self.order_type),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"create_order requires: {', '.join(missing)}")
            order_type = self.order_type
            assert order_type is not None
            if not self.close_position and self.amount is None:
                raise ValueError("create_order requires amount (unless close_position=true)")
            if order_type == "limit" and self.price is None:
                raise ValueError("limit orders require price")
            if order_type in ("stop", "take_profit") and (self.stop_price is None or self.price is None):
                raise ValueError(f"{order_type} orders require stop_price and price")
            if order_type in ("stop_market", "take_profit_market") and self.stop_price is None:
                raise ValueError(f"{order_type} orders require stop_price")
            if order_type == "trailing_stop_market" and self.callback_rate is None:
                raise ValueError("trailing_stop_market orders require callback_rate")
        elif action == "cancel_order":
            if not self.order_id or not self.symbol:
                raise ValueError("cancel_order requires order_id and symbol")
        elif action == "set_leverage":
            if self.leverage is None or not self.symbol:
                raise ValueError("set_leverage requires leverage and symbol")
        elif action == "set_margin_mode":
            if self.margin_mode is None or not self.symbol:
                raise ValueError("set_margin_mode requires margin_mode and symbol")
        elif action == "set_position_mode":
            if self.hedge is None:
                raise ValueError("set_position_mode requires hedge (true=hedge, false=one-way)")
        elif action in ("positions", "open_orders"):
            pass  # symbol optional
        elif action == "balance":
            pass
        return self


class BinancePerpOutput(BaseModel):
    action: str
    dry_run: bool
    exchange: str
    product: str
    ccxt_id: str
    sandbox: bool
    planned: dict[str, Any] | None = None
    result: dict[str, Any] | list[Any] | None = None


class BinancePerpTool(BaseTool):
    name: ClassVar[str] = "binance_perp_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "execution"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = BinancePerpInput
    output_model: ClassVar[type[BaseModel]] = BinancePerpOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        from runtime.config_loader import load_config
        from runtime.exchange_resolve import resolve_exchange

        parsed = BinancePerpInput(**inputs)
        cfg = load_config()
        exec_cfg = cfg.execution.binance_perp
        resolved = resolve_exchange(cfg, exec_cfg.exchange, exec_cfg.product)

        meta = {
            "action": parsed.action,
            "dry_run": parsed.dry_run,
            "exchange": resolved.exchange,
            "product": resolved.product,
            "ccxt_id": resolved.ccxt_id,
            "sandbox": resolved.sandbox,
        }

        if parsed.action in WRITE_ACTIONS and parsed.dry_run:
            planned = self._planned_payload(parsed)
            output = self.output_model(**meta, planned=planned, result=None)
            return ToolResult(success=True, data=output.model_dump())

        result_payload = await self._run_exchange(resolved, parsed)
        output = self.output_model(**meta, planned=None, result=result_payload)
        return ToolResult(success=True, data=output.model_dump())

    def _planned_payload(self, parsed: BinancePerpInput) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": parsed.action}
        for field in (
            "symbol",
            "side",
            "order_type",
            "amount",
            "price",
            "stop_price",
            "callback_rate",
            "activation_price",
            "order_id",
            "leverage",
            "margin_mode",
            "reduce_only",
            "close_position",
            "position_side",
            "working_type",
            "hedge",
        ):
            value = getattr(parsed, field)
            if value is not None:
                payload[field] = value
        return payload

    async def _run_exchange(self, resolved: Any, parsed: BinancePerpInput) -> dict[str, Any] | list[Any]:
        import ccxt.async_support as ccxt

        exchange_class = getattr(ccxt, resolved.ccxt_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported exchange: {resolved.ccxt_id}")

        exchange = exchange_class(resolved.ccxt_options())
        try:
            if resolved.sandbox and hasattr(exchange, "set_sandbox_mode"):
                await exchange.set_sandbox_mode(True)

            action = parsed.action
            if action == "balance":
                raw = await exchange.fetch_balance()
                return self._trim_balance(raw)
            if action == "positions":
                raw = await exchange.fetch_positions(
                    [parsed.symbol] if parsed.symbol else None
                )
                return [self._trim_position(p) for p in raw]
            if action == "open_orders":
                raw = await exchange.fetch_open_orders(parsed.symbol)
                return [self._trim_order(o) for o in raw]
            if action == "create_order":
                return self._trim_order(await self._create_order(exchange, parsed))
            if action == "cancel_order":
                assert parsed.order_id and parsed.symbol
                raw = await exchange.cancel_order(parsed.order_id, parsed.symbol)
                return self._trim_order(raw)
            if action == "set_leverage":
                assert parsed.leverage is not None and parsed.symbol
                return await exchange.set_leverage(parsed.leverage, parsed.symbol)
            if action == "set_margin_mode":
                assert parsed.margin_mode and parsed.symbol
                return await exchange.set_margin_mode(parsed.margin_mode, parsed.symbol)
            if action == "set_position_mode":
                assert parsed.hedge is not None
                return await exchange.set_position_mode(parsed.hedge)
            raise ValueError(f"Unsupported action: {action}")
        finally:
            await exchange.close()

    async def _create_order(self, exchange: Any, parsed: BinancePerpInput) -> dict[str, Any]:
        assert parsed.symbol and parsed.side and parsed.order_type
        params: dict[str, Any] = {}
        if parsed.reduce_only:
            params["reduceOnly"] = True
        if parsed.close_position:
            params["closePosition"] = True
        if parsed.position_side is not None:
            params["positionSide"] = parsed.position_side
        if parsed.working_type is not None:
            params["workingType"] = parsed.working_type
        if parsed.order_type in CONDITIONAL_STOP_TYPES and parsed.stop_price is not None:
            params["stopPrice"] = parsed.stop_price
        if parsed.order_type == "trailing_stop_market":
            params["callbackRate"] = parsed.callback_rate
            if parsed.activation_price is not None:
                params["activationPrice"] = parsed.activation_price

        amount = parsed.amount if parsed.amount is not None else 0.0
        price = parsed.price
        return await exchange.create_order(
            parsed.symbol,
            parsed.order_type,
            parsed.side,
            amount,
            price,
            params,
        )

    def _trim_balance(self, raw: dict[str, Any]) -> dict[str, Any]:
        total = raw.get("total") or {}
        free = raw.get("free") or {}
        used = raw.get("used") or {}
        assets = sorted(
            {
                asset
                for asset in set(total) | set(free) | set(used)
                if any(
                    isinstance(qty, (int, float)) and qty
                    for qty in (total.get(asset), free.get(asset), used.get(asset))
                )
            }
        )
        return {
            "assets": {
                asset: {
                    "free": free.get(asset),
                    "used": used.get(asset),
                    "total": total.get(asset),
                }
                for asset in assets
            },
            "info_keys": sorted(raw.get("info", {}).keys()) if isinstance(raw.get("info"), dict) else [],
        }

    def _trim_position(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "symbol": raw.get("symbol"),
            "side": raw.get("side"),
            "contracts": raw.get("contracts"),
            "contractSize": raw.get("contractSize"),
            "entryPrice": raw.get("entryPrice"),
            "markPrice": raw.get("markPrice"),
            "notional": raw.get("notional"),
            "leverage": raw.get("leverage"),
            "unrealizedPnl": raw.get("unrealizedPnl"),
            "marginMode": raw.get("marginMode"),
            "hedged": raw.get("hedged"),
            "percentage": raw.get("percentage"),
        }

    def _trim_order(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw.get("id"),
            "clientOrderId": raw.get("clientOrderId"),
            "symbol": raw.get("symbol"),
            "type": raw.get("type"),
            "side": raw.get("side"),
            "price": raw.get("price"),
            "amount": raw.get("amount"),
            "filled": raw.get("filled"),
            "remaining": raw.get("remaining"),
            "status": raw.get("status"),
            "reduceOnly": raw.get("reduceOnly"),
            "stopPrice": raw.get("stopPrice"),
            "timestamp": raw.get("timestamp"),
        }
