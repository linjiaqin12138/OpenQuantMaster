from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.models.result import Result, ServiceResult
from src.providers.ccxt import (
    CcxtVenue,
    cancel_order_result,
    create_order_result,
    fetch_balance_result,
    fetch_open_orders_result,
    fetch_positions_result,
    set_leverage_result,
    set_margin_mode_result,
    set_position_mode_result,
)
from src.use_cases.base import BaseUseCase, provider_failure

OrderType = Literal[
    "market",
    "limit",
    "stop_market",
    "take_profit_market",
    "stop",
    "take_profit",
    "trailing_stop_market",
]

CONDITIONAL_STOP_TYPES: frozenset[str] = frozenset(
    {
        "stop_market",
        "take_profit_market",
        "stop",
        "take_profit",
    }
)

_EXCHANGE_ERROR_CODES = {
    "provider_timeout": "exchange_unavailable",
    "provider_unavailable": "exchange_unavailable",
    "provider_rate_limited": "exchange_unavailable",
    "provider_rejected": "order_rejected",
    "provider_unauthorized": "order_rejected",
}


class FetchBalanceInput(BaseModel):
    """Request for the account balance."""


class FetchPositionsInput(BaseModel):
    """Request for the open positions."""

    symbol: str | None = None


class FetchOpenOrdersInput(BaseModel):
    """Request for the resting and conditional orders."""

    symbol: str = Field(..., min_length=1)
    include_conditional: bool = True


class CreateOrderInput(BaseModel):
    """Request to open an order."""

    symbol: str = Field(..., min_length=1)
    side: Literal["buy", "sell"]
    order_type: OrderType
    amount: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    callback_rate: float | None = Field(default=None, ge=0.1, le=10)
    activation_price: float | None = Field(default=None, gt=0)
    reduce_only: bool = False
    close_position: bool = False
    position_side: Literal["BOTH", "LONG", "SHORT"] | None = None
    working_type: Literal["CONTRACT_PRICE", "MARK_PRICE"] | None = None
    dry_run: bool = True

    @model_validator(mode="after")
    def validate_order(self) -> CreateOrderInput:
        if not self.close_position and self.amount is None:
            raise ValueError("amount is required unless close_position=true")
        if self.order_type == "limit" and self.price is None:
            raise ValueError("limit orders require price")
        if self.order_type in ("stop", "take_profit") and (
            self.stop_price is None or self.price is None
        ):
            raise ValueError(f"{self.order_type} orders require stop_price and price")
        if self.order_type in ("stop_market", "take_profit_market") and self.stop_price is None:
            raise ValueError(f"{self.order_type} orders require stop_price")
        if self.order_type == "trailing_stop_market" and self.callback_rate is None:
            raise ValueError("trailing_stop_market orders require callback_rate")
        return self


class CancelOrderInput(BaseModel):
    """Request to cancel an open order."""

    order_id: str = Field(..., min_length=1)
    symbol: str = Field(..., min_length=1)
    dry_run: bool = True


class SetLeverageInput(BaseModel):
    """Request to set the leverage of one symbol."""

    leverage: int = Field(..., ge=1, le=125)
    symbol: str = Field(..., min_length=1)
    dry_run: bool = True


class SetMarginModeInput(BaseModel):
    """Request to set the margin mode of one symbol."""

    margin_mode: Literal["isolated", "cross"]
    symbol: str = Field(..., min_length=1)
    dry_run: bool = True


class SetPositionModeInput(BaseModel):
    """Request to switch between hedge and one-way position mode."""

    hedge: bool
    dry_run: bool = True


class AssetBalance(BaseModel):
    free: float | None = None
    used: float | None = None
    total: float | None = None


class FetchBalanceOutput(BaseModel):
    """Response of the balance action."""

    assets: dict[str, AssetBalance]
    info_keys: list[str]


class FetchPositionsOutput(BaseModel):
    """Response of the positions action."""

    positions: list[dict[str, Any]]


class FetchOpenOrdersOutput(BaseModel):
    """Response of the open-orders action."""

    orders: list[dict[str, Any]]


class CreateOrderOutput(BaseModel):
    """Response of the order creation."""

    dry_run: bool
    planned: dict[str, Any] | None = None
    order: dict[str, Any] | None = None


class CancelOrderOutput(BaseModel):
    """Response of the order cancellation."""

    dry_run: bool
    planned: dict[str, Any] | None = None
    order: dict[str, Any] | None = None


class SetLeverageOutput(BaseModel):
    """Response of the leverage change."""

    dry_run: bool
    planned: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class SetMarginModeOutput(BaseModel):
    """Response of the margin-mode change."""

    dry_run: bool
    planned: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class SetPositionModeOutput(BaseModel):
    """Response of the position-mode change."""

    dry_run: bool
    planned: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class BinancePerpUseCaseConfig(BaseModel):
    """Settings of the perpetual-futures workflows."""

    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "usdm"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""


class _BinancePerpUseCase(BaseUseCase):
    """Shared venue handling of the perpetual-futures workflows."""

    def __init__(self, config: BinancePerpUseCaseConfig) -> None:
        self._config = config

    def _venue(self) -> CcxtVenue:
        config = self._config
        return CcxtVenue(
            exchange=config.exchange,
            product=config.product,
            sandbox=config.sandbox,
            api_key=config.api_key,
            secret=config.secret,
        )

    def _failure(self, result: Result) -> ServiceResult:
        return provider_failure(
            result.error,
            codes=_EXCHANGE_ERROR_CODES,
            default="exchange_failed",
        )


class FetchBalanceUseCase(_BinancePerpUseCase):
    """Read the account balance."""

    input_model = FetchBalanceInput
    output_model = FetchBalanceOutput

    async def _run(self, inputs: FetchBalanceInput) -> ServiceResult:
        result = await fetch_balance_result(venue=self._venue())
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=FetchBalanceOutput(
                assets=result.data["assets"],
                info_keys=result.data["info_keys"],
            ),
        )


class FetchPositionsUseCase(_BinancePerpUseCase):
    """Read the open positions."""

    input_model = FetchPositionsInput
    output_model = FetchPositionsOutput

    async def _run(self, inputs: FetchPositionsInput) -> ServiceResult:
        result = await fetch_positions_result(venue=self._venue(), symbol=inputs.symbol)
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=FetchPositionsOutput(positions=result.data),
        )


class FetchOpenOrdersUseCase(_BinancePerpUseCase):
    """Read the resting and conditional orders."""

    input_model = FetchOpenOrdersInput
    output_model = FetchOpenOrdersOutput

    async def _run(self, inputs: FetchOpenOrdersInput) -> ServiceResult:
        result = await fetch_open_orders_result(
            venue=self._venue(),
            symbol=inputs.symbol,
            include_conditional=inputs.include_conditional,
        )
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=FetchOpenOrdersOutput(orders=result.data),
        )


class CreateOrderUseCase(_BinancePerpUseCase):
    """Open an order on the perpetual-futures market."""

    input_model = CreateOrderInput
    output_model = CreateOrderOutput

    async def _run(self, inputs: CreateOrderInput) -> ServiceResult:
        if inputs.dry_run:
            return ServiceResult(
                success=True,
                data=CreateOrderOutput(dry_run=True, planned=_planned(inputs), order=None),
            )
        result = await create_order_result(
            venue=self._venue(),
            symbol=inputs.symbol,
            order_type=inputs.order_type,
            side=inputs.side,
            amount=inputs.amount if inputs.amount is not None else 0.0,
            price=inputs.price,
            params=_order_params(inputs),
        )
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=CreateOrderOutput(dry_run=False, planned=None, order=result.data),
        )


class CancelOrderUseCase(_BinancePerpUseCase):
    """Cancel an open order."""

    input_model = CancelOrderInput
    output_model = CancelOrderOutput

    async def _run(self, inputs: CancelOrderInput) -> ServiceResult:
        if inputs.dry_run:
            return ServiceResult(
                success=True,
                data=CancelOrderOutput(dry_run=True, planned=_planned(inputs), order=None),
            )
        result = await cancel_order_result(
            venue=self._venue(),
            order_id=inputs.order_id,
            symbol=inputs.symbol,
        )
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=CancelOrderOutput(dry_run=False, planned=None, order=result.data),
        )


class SetLeverageUseCase(_BinancePerpUseCase):
    """Set the leverage of one symbol."""

    input_model = SetLeverageInput
    output_model = SetLeverageOutput

    async def _run(self, inputs: SetLeverageInput) -> ServiceResult:
        if inputs.dry_run:
            return ServiceResult(
                success=True,
                data=SetLeverageOutput(dry_run=True, planned=_planned(inputs), result=None),
            )
        result = await set_leverage_result(
            venue=self._venue(),
            leverage=inputs.leverage,
            symbol=inputs.symbol,
        )
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=SetLeverageOutput(dry_run=False, planned=None, result=result.data),
        )


class SetMarginModeUseCase(_BinancePerpUseCase):
    """Set the margin mode of one symbol."""

    input_model = SetMarginModeInput
    output_model = SetMarginModeOutput

    async def _run(self, inputs: SetMarginModeInput) -> ServiceResult:
        if inputs.dry_run:
            return ServiceResult(
                success=True,
                data=SetMarginModeOutput(dry_run=True, planned=_planned(inputs), result=None),
            )
        result = await set_margin_mode_result(
            venue=self._venue(),
            margin_mode=inputs.margin_mode,
            symbol=inputs.symbol,
        )
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=SetMarginModeOutput(dry_run=False, planned=None, result=result.data),
        )


class SetPositionModeUseCase(_BinancePerpUseCase):
    """Switch between hedge and one-way position mode."""

    input_model = SetPositionModeInput
    output_model = SetPositionModeOutput

    async def _run(self, inputs: SetPositionModeInput) -> ServiceResult:
        if inputs.dry_run:
            return ServiceResult(
                success=True,
                data=SetPositionModeOutput(dry_run=True, planned=_planned(inputs), result=None),
            )
        result = await set_position_mode_result(venue=self._venue(), hedge=inputs.hedge)
        if not result.success:
            return self._failure(result)
        return ServiceResult(
            success=True,
            data=SetPositionModeOutput(dry_run=False, planned=None, result=result.data),
        )


def _planned(inputs: BaseModel) -> dict[str, Any]:
    return inputs.model_dump(exclude={"dry_run"}, exclude_none=True)


def _order_params(inputs: CreateOrderInput) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if inputs.reduce_only:
        params["reduceOnly"] = True
    if inputs.close_position:
        params["closePosition"] = True
    if inputs.position_side is not None:
        params["positionSide"] = inputs.position_side
    if inputs.working_type is not None:
        params["workingType"] = inputs.working_type
    if inputs.order_type in CONDITIONAL_STOP_TYPES and inputs.stop_price is not None:
        params["stopPrice"] = inputs.stop_price
    if inputs.order_type == "trailing_stop_market":
        params["callbackRate"] = inputs.callback_rate
        if inputs.activation_price is not None:
            params["activationPrice"] = inputs.activation_price
    return params
