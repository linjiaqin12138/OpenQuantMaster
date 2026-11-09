from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from src.models.result import ServiceResult
from src.services.base import BaseService
from src.use_cases.indicator import (
    ComputeIndicatorsInput,
    ComputeIndicatorsOutput,
    ComputeIndicatorsUseCase,
)
from src.use_cases.ohlcv import FetchBarsUseCase, FetchBarsUseCaseConfig

__all__ = [
    "ComputeIndicatorsInput",
    "ComputeIndicatorsOutput",
    "Indicator",
    "IndicatorServiceConfig",
]


class IndicatorServiceConfig(BaseModel):
    """Configuration of the technical-analysis capability."""

    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "spot"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""
    tushare_token: str = ""


class Indicator(BaseService):
    """Technical-analysis capability: indicators and candlestick patterns."""

    def __init__(self, config: IndicatorServiceConfig) -> None:
        self.config = config
        fetch_bars = FetchBarsUseCase(
            FetchBarsUseCaseConfig(
                exchange=config.exchange,
                product=config.product,
                sandbox=config.sandbox,
                api_key=config.api_key,
                secret=config.secret,
                tushare_token=config.tushare_token,
            )
        )
        self._compute_indicators = ComputeIndicatorsUseCase(fetch_bars)

    async def compute(
        self,
        request: ComputeIndicatorsInput | dict[str, Any],
    ) -> ServiceResult:
        """Compute technical indicators over the given or fetched bars."""
        return await self._compute_indicators.run(request)
