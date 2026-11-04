from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar, Literal, Optional

import numpy as np
import pandas as pd
import structlog
import talib
import talib.abstract as ta
from pydantic import BaseModel, Field, model_validator

from runtime.services.base import BaseService, ServiceResult
from runtime.services.ohlcv import OHLCV

logger = structlog.get_logger()

INDICATOR_ALIASES = {
    "sma": "SMA",
    "ema": "EMA",
    "macd": "MACD",
    "rsi": "RSI",
    "boll": "BBANDS",
    "atr": "ATR",
}

NEUTRAL_PATTERNS = {
    "DOJI",
    "DOJISTAR",
    "DRAGONFLYDOJI",
    "GRAVESTONEDOJI",
    "LONGLEGGEDDOJI",
    "SPINNINGTOP",
    "HIKKAKE",
    "HIKKAKEMOD",
    "HIGHWAVE",
    "RICKSHAWMAN",
}


class IndicatorInput(BaseModel):
    symbol: str | None = None
    market: Literal["crypto", "us_equity", "hk_equity", "a_share"] = "crypto"
    interval: str = "1h"
    limit: int = Field(default=100, ge=1)
    bars: list[dict[str, Any]] | None = None
    indicators: list[str] = Field(
        default_factory=lambda: ["sma", "ema", "macd", "rsi", "boll", "atr"]
    )
    indicator_params: dict[str, dict] = Field(default_factory=dict)
    patterns: list[str] | None = Field(default=None)


class IndicatorInputBarsRequired(IndicatorInput):
    bars: list[dict[str, Any]]


class IndicatorInputWithOHLCV(IndicatorInput):
    @model_validator(mode="after")
    def check_bars_or_symbol(self) -> IndicatorInputWithOHLCV:
        if self.bars is None and not self.symbol:
            raise ValueError("bars or symbol is required")
        return self


class IndicatorOutput(BaseModel):
    symbol: str
    interval: str
    rows: int
    indicators: dict[str, Any]
    patterns: dict[str, Any]
    summary: str


class Indicator(BaseService):
    input_model: ClassVar[type[BaseModel]] = IndicatorInputBarsRequired
    output_model: ClassVar[type[BaseModel]] = IndicatorOutput

    def __init__(self, ohlcv: Optional[OHLCV] = None) -> None:
        self._ohlcv = ohlcv
        self.input_model = IndicatorInputWithOHLCV if ohlcv is not None else IndicatorInputBarsRequired

    async def _run(self, inputs: IndicatorInput) -> ServiceResult:
        indicator_names = inputs.indicators
        indicator_func_names = [_resolve_indicator_name(n) for n in indicator_names]
        valid_funcs = set(talib.get_functions())
        for name, func_name in zip(indicator_names, indicator_func_names):
            if func_name not in valid_funcs:
                return ServiceResult(success=False, error=f"Unknown indicator function: {name}")

        interval = inputs.interval
        if inputs.bars is not None:
            df = self._normalize_ohlcv(pd.DataFrame(inputs.bars))
            symbol = inputs.symbol or ""
        else:
            symbol = str(inputs.symbol)
            df = await self._load_ohlcv_from_symbol(
                symbol=symbol,
                market=inputs.market,
                interval=interval,
                limit=inputs.limit,
            )

        rows = len(df)
        if rows < 2:
            return ServiceResult(success=False, error="OHLCV data requires at least 2 rows")

        indicator_params = {
            _resolve_indicator_name(k): v for k, v in inputs.indicator_params.items()
        }
        patterns = inputs.patterns or []

        required_min_period = self._compute_required_min_period(
            indicator_func_names, patterns, indicator_params, df
        )
        if rows < required_min_period:
            return ServiceResult(
                success=False,
                error=(
                    f"Insufficient data: {rows} rows provided, "
                    f"but at least {required_min_period} rows are required "
                    f"for the configured indicators/patterns"
                ),
            )

        computed_indicators = self._compute_indicators(
            df, indicator_names, indicator_func_names, indicator_params
        )
        computed_patterns = self._compute_patterns(df, patterns)
        summary = self._build_summary(symbol, interval, computed_indicators, computed_patterns)

        output = self.output_model(
            symbol=symbol,
            interval=interval,
            rows=rows,
            indicators=computed_indicators,
            patterns=computed_patterns,
            summary=summary,
        )
        return ServiceResult(success=True, data=output.model_dump())

    async def _load_ohlcv_from_symbol(
        self,
        symbol: str,
        market: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame:
        # Guaranteed by IndicatorInput validation when bars are absent.
        assert self._ohlcv is not None
        result = await self._ohlcv.run(
            {
                "symbol": symbol,
                "market": market,
                "interval": interval,
                "limit": limit,
            }
        )
        if not result.success:
            raise RuntimeError(f"Failed to fetch OHLCV data: {result.error or 'unknown error'}")
        bars = result.data.get("bars") or []
        if not bars:
            raise RuntimeError("Failed to fetch OHLCV data: empty bars")
        return self._normalize_ohlcv(pd.DataFrame(bars))

    def _normalize_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        expected = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise ValueError(f"OHLCV missing columns: {missing}")
        df = df.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["open", "high", "low", "close"])
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df

    def _compute_required_min_period(
        self,
        indicator_names: list[str],
        pattern_names: list[str],
        indicator_params: dict[str, dict],
        df: pd.DataFrame,
    ) -> int:
        periods = [1]
        for name in indicator_names:
            func_name = name.upper()
            params = indicator_params.get(func_name, {})
            try:
                f = ta.Function(func_name, df)
                if params:
                    f.set_parameters(params)
                periods.append(f.lookback)
            except Exception:
                pass
        for name in pattern_names:
            func_name, _ = _normalize_pattern_name(name)
            try:
                f = ta.Function(func_name, df)
                periods.append(f.lookback)
            except Exception:
                pass
        return max(periods)

    def _compute_indicators(
        self,
        df: pd.DataFrame,
        indicator_names: list[str],
        indicator_func_names: list[str],
        indicator_params: dict[str, dict],
    ) -> dict[str, Any]:
        indicators: dict[str, Any] = {}
        for name, func_name in zip(indicator_names, indicator_func_names):
            params = indicator_params.get(func_name, {})
            try:
                f = ta.Function(func_name, df)
                if params:
                    f.set_parameters(params)
                result = f.run()
                output_names = f.output_names
                params_used = dict(f.get_parameters())
                if len(output_names) == 1:
                    indicators[name] = {
                        "value": _last_value(result),
                        "params": params_used,
                    }
                else:
                    values: dict[str, Any] = {
                        output_name: _last_value(result[output_name])
                        for output_name in output_names
                    }
                    values["params"] = params_used
                    indicators[name] = values
            except Exception as exc:
                indicators[name] = {"error": str(exc)}
        return indicators

    def _compute_patterns(
        self,
        df: pd.DataFrame,
        pattern_names: list[str],
    ) -> dict[str, Any]:
        if not pattern_names:
            return {}

        history: list[dict[str, Any]] = []
        errors: dict[str, str] = {}
        for name in pattern_names:
            func_name, display_name = _normalize_pattern_name(name)
            try:
                f = ta.Function(func_name, df)
                result = f.run()
                for idx in range(len(df)):
                    value = result.iloc[idx]
                    if value == 0:
                        continue
                    label = _pattern_label(display_name, int(value))
                    ts = df["timestamp"].iloc[idx]
                    history.append(
                        {
                            "timestamp": _format_timestamp(ts),
                            "pattern": display_name,
                            "label": label,
                            "strength": int(abs(value)),
                        }
                    )
            except Exception as exc:
                errors[display_name] = str(exc)

        history.sort(key=lambda x: x["timestamp"])

        last_bullish: str | None = None
        last_bearish: str | None = None
        for entry in reversed(history):
            if entry["label"] == "bullish" and last_bullish is None:
                last_bullish = entry["pattern"]
            if entry["label"] == "bearish" and last_bearish is None:
                last_bearish = entry["pattern"]
            if last_bullish is not None and last_bearish is not None:
                break

        patterns: dict[str, Any] = {
            "last_bullish": last_bullish,
            "last_bearish": last_bearish,
            "history": history,
        }
        if errors:
            patterns["errors"] = errors
        return patterns

    def _build_summary(
        self,
        symbol: str,
        interval: str,
        indicators: dict[str, Any],
        patterns: dict[str, Any],
    ) -> str:
        indicator_parts: list[str] = []
        for name, result in indicators.items():
            if "error" in result:
                continue
            display_name = name.upper()
            params = result.get("params", {})
            if "value" in result:
                param_str = _format_params(params)
                value_str = _fmt_value(result["value"])
                indicator_parts.append(f"{display_name}{param_str}={value_str}")
            else:
                for output_name in result:
                    if output_name == "params":
                        continue
                    short_name = _short_output_name(display_name, output_name)
                    value_str = _fmt_value(result[output_name])
                    indicator_parts.append(f"{display_name}.{short_name}={value_str}")

        parts = [f"{symbol} {interval}"]
        if indicator_parts:
            parts.append(" | " + " ".join(indicator_parts))
        if patterns.get("history"):
            latest = patterns["history"][-1]
            direction = {
                "bullish": "看涨",
                "bearish": "看跌",
                "neutral": "中性",
            }.get(latest["label"], latest["label"])
            parts.append(f" | 形态: {direction} {latest['pattern']}")

        return "".join(parts)


def _resolve_indicator_name(name: str) -> str:
    return INDICATOR_ALIASES.get(name.lower(), name.upper())


def _normalize_pattern_name(name: str) -> tuple[str, str]:
    upper = name.upper()
    if upper.startswith("CDL"):
        return upper, upper[3:]
    return f"CDL{upper}", upper


def _pattern_label(display_name: str, value: int) -> str:
    if display_name in NEUTRAL_PATTERNS:
        return "neutral"
    return "bullish" if value > 0 else "bearish"


def _format_params(params: dict[str, Any]) -> str:
    if not params:
        return ""
    return f"({','.join(str(v) for v in params.values())})"


def _short_output_name(func_name: str, output_name: str) -> str:
    prefix = func_name.lower()
    lower = output_name.lower()
    if lower.startswith(prefix) and len(lower) > len(prefix):
        return output_name[len(prefix) :]
    return output_name


def _last_value(arr: Any) -> float | None:
    if arr is None or len(arr) == 0:
        return None
    if hasattr(arr, "iloc"):
        value = arr.iloc[-1]
    else:
        value = arr[-1]
    if np.isnan(value):
        return None
    return float(value)


def _fmt_value(value: Any) -> str:
    f = _get_float(value)
    if f is None:
        return "nan"
    return f"{f:.6g}"


def _get_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        f = float(value)
        if np.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _format_timestamp(ts: Any) -> str:
    if isinstance(ts, pd.Timestamp):
        return ts.isoformat()
    if isinstance(ts, datetime):
        return ts.isoformat()
    return str(ts)
