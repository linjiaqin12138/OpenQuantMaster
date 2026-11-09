from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from src.models.result import ServiceResult
from src.services.base import BaseService
from src.use_cases.ticker import (
    FetchTickerInput,
    FetchTickerOutput,
    FetchTickerUseCase,
    FetchTickerUseCaseConfig,
)

__all__ = [
    "FetchTickerInput",
    "FetchTickerOutput",
    "Ticker",
    "TickerServiceConfig",
]


class TickerServiceConfig(BaseModel):
    """Configuration of the ticker capability."""

    tushare_token: str = ""
    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "spot"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""


class Ticker(BaseService):
    """Latest ticker snapshots for supported markets."""

    def __init__(self, config: TickerServiceConfig) -> None:
        self.config = config
        self._fetch_ticker = FetchTickerUseCase(
            FetchTickerUseCaseConfig(
                tushare_token=config.tushare_token,
                exchange=config.exchange,
                product=config.product,
                sandbox=config.sandbox,
                api_key=config.api_key,
                secret=config.secret,
            )
        )

    async def fetch_ticker(
        self,
        request: FetchTickerInput | dict[str, Any],
    ) -> ServiceResult:
        """Fetch the latest ticker snapshot for one symbol."""
        return await self._fetch_ticker.run(request)
