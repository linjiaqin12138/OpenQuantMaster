from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from src.models.result import ServiceResult
from src.services.base import BaseService
from src.use_cases.binance_perp import (
    BinancePerpUseCaseConfig,
    CancelOrderInput,
    CancelOrderOutput,
    CancelOrderUseCase,
    CreateOrderInput,
    CreateOrderOutput,
    CreateOrderUseCase,
    FetchBalanceInput,
    FetchBalanceOutput,
    FetchBalanceUseCase,
    FetchOpenOrdersInput,
    FetchOpenOrdersOutput,
    FetchOpenOrdersUseCase,
    FetchPositionsInput,
    FetchPositionsOutput,
    FetchPositionsUseCase,
    SetLeverageInput,
    SetLeverageOutput,
    SetLeverageUseCase,
    SetMarginModeInput,
    SetMarginModeOutput,
    SetMarginModeUseCase,
    SetPositionModeInput,
    SetPositionModeOutput,
    SetPositionModeUseCase,
)

__all__ = [
    "BinancePerp",
    "BinancePerpServiceConfig",
    "CancelOrderInput",
    "CancelOrderOutput",
    "CreateOrderInput",
    "CreateOrderOutput",
    "FetchBalanceInput",
    "FetchBalanceOutput",
    "FetchOpenOrdersInput",
    "FetchOpenOrdersOutput",
    "FetchPositionsInput",
    "FetchPositionsOutput",
    "SetLeverageInput",
    "SetLeverageOutput",
    "SetMarginModeInput",
    "SetMarginModeOutput",
    "SetPositionModeInput",
    "SetPositionModeOutput",
]


class BinancePerpServiceConfig(BaseModel):
    """Configuration of the perpetual-futures capability."""

    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "usdm"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""


class BinancePerp(BaseService):
    """Perpetual-futures capability: account queries and exchange actions."""

    def __init__(self, config: BinancePerpServiceConfig) -> None:
        self.config = config
        use_case_config = BinancePerpUseCaseConfig(
            exchange=config.exchange,
            product=config.product,
            sandbox=config.sandbox,
            api_key=config.api_key,
            secret=config.secret,
        )
        self._fetch_balance = FetchBalanceUseCase(use_case_config)
        self._fetch_positions = FetchPositionsUseCase(use_case_config)
        self._fetch_open_orders = FetchOpenOrdersUseCase(use_case_config)
        self._create_order = CreateOrderUseCase(use_case_config)
        self._cancel_order = CancelOrderUseCase(use_case_config)
        self._set_leverage = SetLeverageUseCase(use_case_config)
        self._set_margin_mode = SetMarginModeUseCase(use_case_config)
        self._set_position_mode = SetPositionModeUseCase(use_case_config)

    async def balance(
        self,
        request: FetchBalanceInput | dict[str, Any] | None = None,
    ) -> ServiceResult:
        """Fetch the account balance."""
        return await self._fetch_balance.run(request if request is not None else {})

    async def positions(
        self,
        request: FetchPositionsInput | dict[str, Any],
    ) -> ServiceResult:
        """Fetch the open positions, optionally for one symbol."""
        return await self._fetch_positions.run(request)

    async def open_orders(
        self,
        request: FetchOpenOrdersInput | dict[str, Any],
    ) -> ServiceResult:
        """Fetch the resting orders and, by default, the conditional ones."""
        return await self._fetch_open_orders.run(request)

    async def create_order(
        self,
        request: CreateOrderInput | dict[str, Any],
    ) -> ServiceResult:
        """Open an order; write actions are previewed unless ``dry_run`` is false."""
        return await self._create_order.run(request)

    async def cancel_order(
        self,
        request: CancelOrderInput | dict[str, Any],
    ) -> ServiceResult:
        """Cancel an open order; write actions are previewed unless ``dry_run`` is false."""
        return await self._cancel_order.run(request)

    async def set_leverage(
        self,
        request: SetLeverageInput | dict[str, Any],
    ) -> ServiceResult:
        """Set the leverage of one symbol."""
        return await self._set_leverage.run(request)

    async def set_margin_mode(
        self,
        request: SetMarginModeInput | dict[str, Any],
    ) -> ServiceResult:
        """Set the margin mode of one symbol."""
        return await self._set_margin_mode.run(request)

    async def set_position_mode(
        self,
        request: SetPositionModeInput | dict[str, Any],
    ) -> ServiceResult:
        """Switch between hedge and one-way position mode."""
        return await self._set_position_mode.run(request)
