from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal

import pandas as pd
import structlog
from pydantic import BaseModel, Field

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult

logger = structlog.get_logger()


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
    artifact: str


class OHLCVTool(BaseTool):
    name: ClassVar[str] = "ohlcv_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "market_data"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = OHLCVInput
    output_model: ClassVar[type[BaseModel]] = OHLCVOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        from runtime.config_loader import load_config

        cfg = load_config()
        symbol = inputs["symbol"]
        market = inputs["market"]
        interval = inputs["interval"]
        source = inputs.get("source")

        if market == "crypto" or source == "ccxt":
            df = await self._fetch_crypto(cfg, symbol, interval, inputs)
        elif market in ("us_equity", "hk_equity") or source == "yfinance":
            df = await asyncio.to_thread(self._fetch_yfinance, symbol, interval, inputs)
        elif market == "a_share":
            df = await self._fetch_a_share(cfg, symbol, interval, inputs)
        else:
            return ToolResult(success=False, error=f"Unsupported market: {market}")

        csv_content = self._dataframe_to_csv(df)
        artifact_name = f"ohlcv_{symbol.replace('/', '_')}_{interval}.csv"
        artifact = ArtifactRef(
            name=artifact_name,
            mime_type="text/csv",
            relative_path=artifact_name,
            sha256="",  # runner fills real hash from content
            content=csv_content,
        )
        output = self.output_model(
            symbol=symbol,
            market=market,
            interval=interval,
            rows=len(df),
            artifact=artifact_name,
        )
        return ToolResult(success=True, data=output.model_dump(), artifacts=[artifact])

    async def _fetch_crypto(
        self,
        cfg: Any,
        symbol: str,
        interval: str,
        inputs: dict[str, Any],
    ) -> pd.DataFrame:
        import ccxt.async_support as ccxt

        exchange_id = cfg.market_data.crypto.default_exchange
        exchange_class = getattr(ccxt, exchange_id, None)
        if exchange_class is None:
            raise ValueError(f"Unsupported crypto exchange: {exchange_id}")

        keys = cfg.market_data.crypto.exchange_keys.get(exchange_id, {})
        exchange = exchange_class({"enableRateLimit": True, **keys})
        if cfg.market_data.crypto.sandbox:
            if hasattr(exchange, "set_sandbox_mode"):
                await exchange.set_sandbox_mode(True)

        start_ms = self._iso_to_ms(inputs.get("start"))
        end_ms = self._iso_to_ms(inputs.get("end"))
        limit = inputs.get("limit", 1000)
        try:
            if start_ms is not None:
                since = start_ms
                raw = await exchange.fetch_ohlcv(symbol, interval, since=since, limit=limit)
            else:
                raw = await exchange.fetch_ohlcv(symbol, interval, limit=limit)
        finally:
            await exchange.close()

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if end_ms is not None:
            df = df[df["timestamp"] <= end_ms]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df

    def _fetch_yfinance(
        self,
        symbol: str,
        interval: str,
        inputs: dict[str, Any],
    ) -> pd.DataFrame:
        import yfinance as yf

        ticker = yf.Ticker(symbol)
        kwargs: dict[str, Any] = {"interval": interval}
        if inputs.get("start"):
            kwargs["start"] = inputs["start"][:10]
        if inputs.get("end"):
            kwargs["end"] = inputs["end"][:10]
        if not kwargs.get("start"):
            kwargs["period"] = "max" if inputs.get("limit", 1000) > 100 else "1y"
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

    async def _fetch_a_share(
        self,
        cfg: Any,
        symbol: str,
        interval: str,
        inputs: dict[str, Any],
    ) -> pd.DataFrame:
        source = inputs.get("source")
        token = cfg.market_data.equities.tushare_token
        if source == "tushare" or (source is None and token):
            try:
                return await asyncio.to_thread(
                    self._fetch_tushare, symbol, interval, inputs, token
                )
            except Exception as exc:
                logger.warning(
                    "ohlcv.tushare_failed",
                    symbol=symbol,
                    interval=interval,
                    error=str(exc),
                )
                if source == "tushare":
                    raise
        return await asyncio.to_thread(self._fetch_akshare, symbol, interval, inputs)

    def _fetch_tushare(
        self,
        symbol: str,
        interval: str,
        inputs: dict[str, Any],
        token: str,
    ) -> pd.DataFrame:
        import tushare as ts

        ts.set_token(token)
        pro = ts.pro_api()
        start = inputs.get("start", "")[:10].replace("-", "")
        end = inputs.get("end", "")[:10].replace("-", "")
        df = pro.daily(ts_code=symbol, start_date=start or None, end_date=end or None)
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

    def _fetch_akshare(
        self,
        symbol: str,
        interval: str,
        inputs: dict[str, Any],
    ) -> pd.DataFrame:
        import akshare as ak

        # Strip exchange suffix, e.g. 000001.SZ -> 000001
        code = symbol.split(".")[0]
        start = inputs.get("start", "")[:10].replace("-", "")
        end = inputs.get("end", "")[:10].replace("-", "")
        period = self._map_akshare_period(interval)
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

    def _dataframe_to_csv(self, df: pd.DataFrame) -> str:
        return df.to_csv(index=False)

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
