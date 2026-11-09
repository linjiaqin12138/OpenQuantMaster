from __future__ import annotations

from typing import Literal

import structlog
from pydantic import BaseModel, Field

from src.models.bar import Bar
from src.models.result import Result, ServiceResult
from src.providers.akshare import fetch_a_share_ohlcv_result as fetch_akshare_ohlcv_result
from src.providers.ccxt import CcxtVenue, fetch_crypto_ohlcv_result
from src.providers.tushare import fetch_a_share_ohlcv_result as fetch_tushare_ohlcv_result
from src.providers.yfinance import fetch_equity_ohlcv_result
from src.use_cases.base import BaseUseCase, provider_failure
from src.utils.time import parse_iso_to_ms

logger = structlog.get_logger()

Market = Literal["crypto", "us_equity", "hk_equity", "a_share"]
Source = Literal["ccxt", "yfinance", "tushare", "akshare"]

_ALLOWED_SOURCES: dict[Market, frozenset[str]] = {
    "crypto": frozenset({"ccxt"}),
    "us_equity": frozenset({"yfinance"}),
    "hk_equity": frozenset({"yfinance"}),
    "a_share": frozenset({"tushare", "akshare"}),
}

_MARKET_DATA_ERROR_CODES = {
    "provider_timeout": "market_data_unavailable",
    "provider_unavailable": "market_data_unavailable",
    "provider_rate_limited": "market_data_unavailable",
    "provider_rejected": "market_data_rejected",
    "provider_unauthorized": "market_data_rejected",
    "provider_unsupported_venue": "unsupported_market",
}


class FetchBarsInput(BaseModel):
    """Request of the market-data action."""

    symbol: str = Field(..., min_length=1)
    market: Market
    interval: str = Field(..., min_length=1)
    start: str | None = None
    end: str | None = None
    limit: int = Field(default=1000, ge=1, le=5000)
    source: Source | None = None


class FetchBarsOutput(BaseModel):
    """Response of the market-data action."""

    symbol: str
    market: str
    interval: str
    rows: int
    bars: list[Bar]


class FetchBarsUseCaseConfig(BaseModel):
    """Settings of the market-data workflow."""

    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "spot"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""
    tushare_token: str = ""


class FetchBarsUseCase(BaseUseCase[FetchBarsInput, FetchBarsOutput]):
    """Fetch OHLCV bars for one symbol from the market-data provider of its market."""

    input_model = FetchBarsInput
    output_model = FetchBarsOutput

    def __init__(self, config: FetchBarsUseCaseConfig) -> None:
        self._config = config

    async def _run(self, inputs: FetchBarsInput) -> ServiceResult:
        source = self._resolve_source(inputs)
        if source is None:
            return ServiceResult.from_error(
                "unsupported_source",
                f"Source {inputs.source!r} is not available for market {inputs.market!r}",
            )

        if source == "ccxt":
            result = await self._fetch_crypto(inputs)
        elif source == "yfinance":
            result = await self._fetch_equity(inputs)
        elif source == "tushare":
            result = await self._fetch_tushare(inputs)
            if not result.success and inputs.source is None:
                logger.warning(
                    "ohlcv.tushare_failed",
                    symbol=inputs.symbol,
                    interval=inputs.interval,
                    error=result.error.message if result.error else "unknown error",
                )
                result = await self._fetch_akshare(inputs)
        else:
            result = await self._fetch_akshare(inputs)

        if not result.success:
            return provider_failure(
                result.error,
                codes=_MARKET_DATA_ERROR_CODES,
                default="market_data_failed",
            )

        output = FetchBarsOutput(
            symbol=inputs.symbol,
            market=inputs.market,
            interval=inputs.interval,
            rows=len(result.data),
            bars=result.data,
        )
        return ServiceResult(success=True, data=output)

    def _resolve_source(self, inputs: FetchBarsInput) -> Source | None:
        if inputs.source is not None:
            if inputs.source not in _ALLOWED_SOURCES[inputs.market]:
                return None
            return inputs.source
        if inputs.market == "crypto":
            return "ccxt"
        if inputs.market in ("us_equity", "hk_equity"):
            return "yfinance"
        return "tushare" if self._config.tushare_token else "akshare"

    async def _fetch_crypto(self, inputs: FetchBarsInput) -> Result:
        venue = CcxtVenue(
            exchange=self._config.exchange,
            product=self._config.product,
            sandbox=self._config.sandbox,
            api_key=self._config.api_key,
            secret=self._config.secret,
        )
        return await fetch_crypto_ohlcv_result(
            venue=venue,
            symbol=inputs.symbol,
            interval=inputs.interval,
            limit=inputs.limit,
            since_ms=parse_iso_to_ms(inputs.start),
            until_ms=parse_iso_to_ms(inputs.end),
        )

    async def _fetch_equity(self, inputs: FetchBarsInput) -> Result:
        return await fetch_equity_ohlcv_result(
            symbol=inputs.symbol,
            interval=inputs.interval,
            limit=inputs.limit,
            start=inputs.start,
            end=inputs.end,
        )

    async def _fetch_tushare(self, inputs: FetchBarsInput) -> Result:
        return await fetch_tushare_ohlcv_result(
            token=self._config.tushare_token,
            symbol=inputs.symbol,
            start=inputs.start,
            end=inputs.end,
        )

    async def _fetch_akshare(self, inputs: FetchBarsInput) -> Result:
        return await fetch_akshare_ohlcv_result(
            symbol=inputs.symbol,
            interval=inputs.interval,
            start=inputs.start,
            end=inputs.end,
        )
