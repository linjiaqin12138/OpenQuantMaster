from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from src.models.result import ServiceResult
from src.services.base import BaseService
from src.use_cases.ohlcv import (
    FetchBarsInput,
    FetchBarsOutput,
    FetchBarsUseCase,
    FetchBarsUseCaseConfig,
)

__all__ = [
    "FetchBarsInput",
    "FetchBarsOutput",
    "OHLCV",
    "OHLCVServiceConfig",
]


class OHLCVServiceConfig(BaseModel):
    """Configuration of the market-data capability."""

    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "spot"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""
    tushare_token: str = ""


class OHLCV(BaseService):
    """Market-data capability: OHLCV bars for one symbol."""

    def __init__(self, config: OHLCVServiceConfig) -> None:
        self.config = config
        self._fetch_bars = FetchBarsUseCase(
            FetchBarsUseCaseConfig(
                exchange=config.exchange,
                product=config.product,
                sandbox=config.sandbox,
                api_key=config.api_key,
                secret=config.secret,
                tushare_token=config.tushare_token,
            )
        )

    async def fetch_bars(
        self,
        request: FetchBarsInput | dict[str, Any],
    ) -> ServiceResult:
        """Fetch OHLCV bars for one symbol."""
        return await self._fetch_bars.run(request)
