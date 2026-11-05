from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal

import pandas as pd
import structlog
from pydantic import BaseModel, Field

from src.config import AppConfig
from src.services.base import BaseService, ServiceResult

logger = structlog.get_logger()

# Adapter map only — callers use logical exchange/product names.
_CCXT_EXCHANGE_IDS: dict[tuple[str, str], str] = {
    ("binance", "spot"): "binance",
    ("binance", "usdm"): "binanceusdm",
}


class OHLCVCryptoConfig(BaseModel):
    exchange: str = "binance"
    product: Literal["spot", "usdm"] = "spot"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""


class OHLCVConfig(BaseModel):
    """Parameters this service needs; not the full runtime config."""

    crypto: OHLCVCryptoConfig = Field(default_factory=OHLCVCryptoConfig)
    tushare_token: str = ""

    @classmethod
    def from_config(cls, config: AppConfig) -> OHLCVConfig:
        return cls(
            crypto=OHLCVCryptoConfig(
                api_key=config.providers.binance.api_key,
                secret=config.providers.binance.secret,
            ),
            tushare_token=config.providers.tushare.token,
        )


class OHLCVInput(BaseModel):
    symbol: str = Field(..., min_length=1)
    market: Literal["crypto", "us_equity", "hk_equity", "a_share"]
    interval: str = Field(..., min_length=1)
    start: str | None = None
    end: str | None = None
    limit: int = Field(default=1000, ge=1, le=5000)
    source: Literal["ccxt", "yfinance", "tushare", "akshare"] | None = None


class OHLCVOutput(BaseModel):
    symbol: str
    market: str
    interval: str
    rows: int
    bars: list[dict[str, Any]]


class OHLCV(BaseService):
    input_model: ClassVar[type[BaseModel]] = OHLCVInput
    output_model: ClassVar[type[BaseModel]] = OHLCVOutput

    def __init__(self, cfg: OHLCVConfig) -> None:
        self.cfg = cfg

    async def _run(self, inputs: OHLCVInput) -> ServiceResult:
        symbol = inputs.symbol
        market = inputs.market
        interval = inputs.interval
        source = inputs.source

        if market == "crypto" or source == "ccxt":
            df = await self._fetch_crypto(inputs)
        elif market in ("us_equity", "hk_equity") or source == "yfinance":
            df = await asyncio.to_thread(self._fetch_yfinance, inputs)
        elif market == "a_share":
            df = await self._fetch_a_share(inputs)
        else:
            return ServiceResult.from_error(
                "unsupported_market",
                f"Unsupported market: {market}",
            )

        bars = self._dataframe_to_bars(df)
        output = self.output_model(
            symbol=symbol,
            market=market,
            interval=interval,
            rows=len(bars),
            bars=bars,
        )
        return ServiceResult(success=True, data=output.model_dump())

    async def _fetch_crypto(self, inputs: OHLCVInput) -> pd.DataFrame:
        import ccxt.async_support as ccxt

        crypto = self.cfg.crypto
        adapter_id = _CCXT_EXCHANGE_IDS.get((crypto.exchange, crypto.product))
        if adapter_id is None:
            raise ValueError(
                f"Unsupported crypto venue: exchange={crypto.exchange!r} product={crypto.product!r}"
            )
        exchange_class = getattr(ccxt, adapter_id, None)
        if exchange_class is None:
            raise ValueError(f"Crypto adapter unavailable for venue: {crypto.exchange}/{crypto.product}")

        options: dict[str, str | bool] = {"enableRateLimit": True}
        if crypto.api_key:
            options["apiKey"] = crypto.api_key
        if crypto.secret:
            options["secret"] = crypto.secret
        exchange = exchange_class(options)
        if crypto.sandbox and hasattr(exchange, "set_sandbox_mode"):
            await exchange.set_sandbox_mode(True)

        start_ms = self._iso_to_ms(inputs.start)
        end_ms = self._iso_to_ms(inputs.end)
        limit = inputs.limit
        try:
            if start_ms is not None:
                raw = await exchange.fetch_ohlcv(
                    inputs.symbol, inputs.interval, since=start_ms, limit=limit
                )
            else:
                raw = await exchange.fetch_ohlcv(inputs.symbol, inputs.interval, limit=limit)
        finally:
            await exchange.close()

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if end_ms is not None:
            df = df[df["timestamp"] <= end_ms]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def _fetch_yfinance(self, inputs: OHLCVInput) -> pd.DataFrame:
        import yfinance as yf

        ticker = yf.Ticker(inputs.symbol)
        kwargs: dict[str, Any] = {"interval": inputs.interval}
        if inputs.start:
            kwargs["start"] = inputs.start[:10]
        if inputs.end:
            kwargs["end"] = inputs.end[:10]
        if not kwargs.get("start"):
            kwargs["period"] = "max" if inputs.limit > 100 else "1y"
        hist = ticker.history(**kwargs)
        hist = hist.reset_index()
        hist = hist.rename(
            columns={
                "Date": "timestamp",
                "Datetime": "timestamp",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        hist["timestamp"] = pd.to_datetime(hist["timestamp"], utc=True)
        return hist[["timestamp", "open", "high", "low", "close", "volume"]]

    async def _fetch_a_share(self, inputs: OHLCVInput) -> pd.DataFrame:
        source = inputs.source
        token = self.cfg.tushare_token
        if source == "tushare" or (source is None and token):
            try:
                return await asyncio.to_thread(self._fetch_tushare, inputs, token)
            except Exception as exc:
                logger.warning(
                    "ohlcv.tushare_failed",
                    symbol=inputs.symbol,
                    interval=inputs.interval,
                    error=str(exc),
                )
                if source == "tushare":
                    raise
        return await asyncio.to_thread(self._fetch_akshare, inputs)

    def _fetch_tushare(self, inputs: OHLCVInput, token: str) -> pd.DataFrame:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        start = (inputs.start or "")[:10].replace("-", "")
        end = (inputs.end or "")[:10].replace("-", "")
        df = pro.daily(ts_code=inputs.symbol, start_date=start or None, end_date=end or None)
        df = df.rename(
            columns={
                "trade_date": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "vol": "volume",
            }
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], format="%Y%m%d", utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        return df.sort_values("timestamp").reset_index(drop=True)

    def _fetch_akshare(self, inputs: OHLCVInput) -> pd.DataFrame:
        import akshare as ak

        # Strip exchange suffix, e.g. 000001.SZ -> 000001
        code = inputs.symbol.split(".")[0]
        start = (inputs.start or "")[:10].replace("-", "")
        end = (inputs.end or "")[:10].replace("-", "")
        period = self._map_akshare_period(inputs.interval)
        df = ak.stock_zh_a_hist(
            symbol=code,
            period=period,
            start_date=start or "19700101",
            end_date=end or "20991231",
            adjust="",
        )
        df = df.rename(
            columns={
                "日期": "timestamp",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
            }
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df[["timestamp", "open", "high", "low", "close", "volume"]]

    def _dataframe_to_bars(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        out = df.copy()
        if "timestamp" in out.columns:
            out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True).dt.strftime(
                "%Y-%m-%dT%H:%M:%S%z"
            )
        return out.to_dict(orient="records")

    def _iso_to_ms(self, value: str | None) -> int | None:
        if value is None:
            return None
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    def _map_akshare_period(self, interval: str) -> str:
        mapping = {
            "1d": "daily",
            "d": "daily",
            "D": "daily",
            "1w": "weekly",
            "w": "weekly",
            "W": "weekly",
            "1M": "monthly",
            "m": "monthly",
            "M": "monthly",
            "monthly": "monthly",
        }
        period = mapping.get(interval)
        if period is None:
            logger.warning(
                "ohlcv.unsupported_a_share_interval",
                interval=interval,
                default="daily",
            )
            return "daily"
        return period
