from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from src.models.result import ServiceResult
from src.providers.ccxt import CcxtVenue, fetch_crypto_ticker_result
from src.providers.tushare import fetch_a_share_ticker_result
from src.use_cases.base import BaseUseCase, provider_failure
from src.utils.symbols import a_share_symbol_candidates
from src.utils.time import format_utc_iso

_NO_MATCH_CODES = frozenset({"symbol_not_found", "no_quote_data"})

_MARKET_DATA_ERROR_CODES = {
    "provider_timeout": "market_data_unavailable",
    "provider_unavailable": "market_data_unavailable",
    "provider_rate_limited": "market_data_unavailable",
    "provider_rejected": "market_data_rejected",
    "provider_unauthorized": "market_data_rejected",
}


class FetchTickerInput(BaseModel):
    """Request for the latest snapshot of one instrument."""

    symbol: str = Field(..., min_length=1)
    market: Literal["a_share", "crypto"]

    @model_validator(mode="after")
    def normalize_symbol(self) -> FetchTickerInput:
        self.symbol = self.symbol.strip()
        if self.market == "a_share" and not a_share_symbol_candidates(self.symbol):
            raise ValueError(
                "symbol must be a six-digit A-share code, optionally with an .SH/.SZ/.BJ suffix"
            )
        return self


class FetchTickerOutput(BaseModel):
    """Latest ticker snapshot with separate quote and fetch timestamps."""

    symbol: str
    market: str
    name: str
    source: str
    price: float
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    change: float | None = None
    change_percent: float | None = None
    bid: float | None = None
    ask: float | None = None
    quote_time: str | None = None
    fetched_at: str


class FetchTickerUseCaseConfig(BaseModel):
    """Settings of the ticker workflow."""

    tushare_token: str = ""
    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "spot"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""


class FetchTickerUseCase(BaseUseCase[FetchTickerInput, FetchTickerOutput]):
    """Fetch one latest ticker through the provider of its market."""

    input_model = FetchTickerInput
    output_model = FetchTickerOutput

    def __init__(self, config: FetchTickerUseCaseConfig) -> None:
        self._config = config

    async def _run(self, inputs: FetchTickerInput) -> ServiceResult:
        if inputs.market == "crypto":
            return await self._fetch_crypto(inputs)
        return await self._fetch_a_share(inputs)

    async def _fetch_a_share(self, inputs: FetchTickerInput) -> ServiceResult:
        if not self._config.tushare_token:
            return ServiceResult.from_error(
                "missing_provider_token",
                "Tushare token is required to fetch an A-share ticker",
            )

        candidates = a_share_symbol_candidates(inputs.symbol)
        matches: list[tuple[str, dict[str, Any]]] = []
        last_error = None
        for candidate in candidates:
            result = await fetch_a_share_ticker_result(
                token=self._config.tushare_token,
                symbol=candidate,
            )
            if result.success:
                matches.append((candidate, result.data))
                continue
            if result.error is not None and result.error.code not in _NO_MATCH_CODES:
                last_error = result.error

        if len(matches) == 1:
            symbol, data = matches[0]
            return ServiceResult(
                success=True,
                data=FetchTickerOutput(
                    symbol=symbol,
                    market=inputs.market,
                    source="tushare",
                    fetched_at=format_utc_iso(datetime.now(timezone.utc)),
                    **data,
                ),
            )
        if len(matches) > 1:
            listed = ", ".join(
                f"{symbol} ({data.get('name') or 'unknown'})" for symbol, data in matches
            )
            return ServiceResult.from_error(
                "ambiguous_symbol",
                f"{inputs.symbol} matches several listings: {listed}. "
                "Specify the exchange suffix, for example 000300.SH.",
            )
        if last_error is not None:
            return provider_failure(
                last_error,
                codes=_MARKET_DATA_ERROR_CODES,
                default="market_data_failed",
            )
        return ServiceResult.from_error(
            "market_data_failed",
            f"No A-share ticker found for {inputs.symbol}",
        )

    async def _fetch_crypto(self, inputs: FetchTickerInput) -> ServiceResult:
        venue = CcxtVenue(
            exchange=self._config.exchange,
            product=self._crypto_product(inputs.symbol),
            sandbox=self._config.sandbox,
            api_key=self._config.api_key,
            secret=self._config.secret,
        )
        result = await fetch_crypto_ticker_result(venue=venue, symbol=inputs.symbol)
        if not result.success:
            return provider_failure(
                result.error,
                codes=_MARKET_DATA_ERROR_CODES,
                default="market_data_failed",
            )
        return ServiceResult(
            success=True,
            data=FetchTickerOutput(
                symbol=inputs.symbol,
                market=inputs.market,
                source="ccxt",
                fetched_at=format_utc_iso(datetime.now(timezone.utc)),
                **result.data,
            ),
        )

    def _crypto_product(self, symbol: str) -> str:
        """Perpetual symbols such as ``BTC/USDT:USDT`` always use the USDT-M venue."""
        if ":" in symbol:
            return "usdm"
        return self._config.product
