from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import structlog
import talib
import talib.abstract as ta
from pydantic import BaseModel, Field, model_validator

from src.models.bar import Bar
from src.models.result import ServiceResult
from src.use_cases.base import BaseUseCase
from src.use_cases.ohlcv import FetchBarsInput, FetchBarsUseCase, Market

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


class ComputeIndicatorsInput(BaseModel):
    """Request of the technical-analysis action."""

    symbol: str | None = None
    market: Market = "crypto"
    interval: str = "1h"
    limit: int = Field(default=100, ge=1)
    bars: list[Bar] | None = None
    indicators: list[str] = Field(
        default_factory=lambda: ["sma", "ema", "macd", "rsi", "boll", "atr"]
    )
    indicator_params: dict[str, dict] = Field(default_factory=dict)
    patterns: list[str] | None = Field(default=None)

    @model_validator(mode="after")
    def check_bars_or_symbol(self) -> ComputeIndicatorsInput:
        if self.bars is None and not self.symbol:
            raise ValueError("bars or symbol is required")
        return self


class ComputeIndicatorsOutput(BaseModel):
    """Response of the technical-analysis action."""

    symbol: str
    interval: str
    rows: int
    indicators: dict[str, Any]
    patterns: dict[str, Any]
    summary: str


class ComputeIndicatorsUseCase(BaseUseCase[ComputeIndicatorsInput, ComputeIndicatorsOutput]):
    """Compute technical indicators and candlestick patterns over OHLCV bars."""

    input_model = ComputeIndicatorsInput
    output_model = ComputeIndicatorsOutput

    def __init__(self, fetch_bars: FetchBarsUseCase) -> None:
        self._fetch_bars = fetch_bars

    async def _run(self, inputs: ComputeIndicatorsInput) -> ServiceResult:
        indicator_names = inputs.indicators
        indicator_func_names = [_resolve_indicator_name(name) for name in indicator_names]
        valid_funcs = set(talib.get_functions())
        for name, func_name in zip(indicator_names, indicator_func_names):
            if func_name not in valid_funcs:
                return ServiceResult.from_error(
                    "unknown_indicator",
                    f"Unknown indicator function: {name}",
                )

        interval = inputs.interval
        if inputs.bars is not None:
            bars = inputs.bars
            symbol = inputs.symbol or ""
        else:
            symbol = str(inputs.symbol)
            fetched = await self._fetch_bars.run(
                FetchBarsInput(
                    symbol=symbol,
                    market=inputs.market,
                    interval=interval,
                    limit=inputs.limit,
                )
            )
            if not fetched.success:
                return fetched
            bars = [Bar.model_validate(bar) for bar in fetched.data["bars"]]

        df = _to_dataframe(bars)
        rows = len(df)
        if rows < 2:
            return ServiceResult.from_error(
                "insufficient_data",
                "OHLCV data requires at least 2 rows",
            )

        indicator_params = {
            _resolve_indicator_name(key): value for key, value in inputs.indicator_params.items()
        }
        patterns = inputs.patterns or []

        required_min_period = _compute_required_min_period(
            indicator_func_names, patterns, indicator_params, df
        )
        if rows < required_min_period:
            return ServiceResult.from_error(
                "insufficient_data",
                (
                    f"Insufficient data: {rows} rows provided, "
                    f"but at least {required_min_period} rows are required "
                    f"for the configured indicators/patterns"
                ),
            )

        computed_indicators = _compute_indicators(
            df, indicator_names, indicator_func_names, indicator_params
        )
        computed_patterns = _compute_patterns(df, patterns)
        summary = _build_summary(symbol, interval, computed_indicators, computed_patterns)

        output = ComputeIndicatorsOutput(
            symbol=symbol,
            interval=interval,
            rows=rows,
            indicators=computed_indicators,
            patterns=computed_patterns,
            summary=summary,
        )
        return ServiceResult(success=True, data=output)


def _to_dataframe(bars: list[Any]) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "timestamp": bar.timestamp,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume if bar.volume is not None else 0.0,
            }
            for bar in bars
        ]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df.sort_values("timestamp").reset_index(drop=True)


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


def _compute_required_min_period(
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
            function = ta.Function(func_name, df)
            if params:
                function.set_parameters(params)
            periods.append(function.lookback)
        except Exception:
            pass
    for name in pattern_names:
        func_name, _ = _normalize_pattern_name(name)
        try:
            periods.append(ta.Function(func_name, df).lookback)
        except Exception:
            pass
    return max(periods)


def _compute_indicators(
    df: pd.DataFrame,
    indicator_names: list[str],
    indicator_func_names: list[str],
    indicator_params: dict[str, dict],
) -> dict[str, Any]:
    indicators: dict[str, Any] = {}
    for name, func_name in zip(indicator_names, indicator_func_names):
        params = indicator_params.get(func_name, {})
        try:
            function = ta.Function(func_name, df)
            if params:
                function.set_parameters(params)
            result = function.run()
            output_names = function.output_names
            params_used = dict(function.get_parameters())
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


def _compute_patterns(df: pd.DataFrame, pattern_names: list[str]) -> dict[str, Any]:
    if not pattern_names:
        return {}

    history: list[dict[str, Any]] = []
    errors: dict[str, str] = {}
    for name in pattern_names:
        func_name, display_name = _normalize_pattern_name(name)
        try:
            result = ta.Function(func_name, df).run()
            for idx in range(len(df)):
                value = result.iloc[idx]
                if value == 0:
                    continue
                history.append(
                    {
                        "timestamp": _format_timestamp(df["timestamp"].iloc[idx]),
                        "pattern": display_name,
                        "label": _pattern_label(display_name, int(value)),
                        "strength": int(abs(value)),
                    }
                )
        except Exception as exc:
            errors[display_name] = str(exc)

    history.sort(key=lambda entry: entry["timestamp"])

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


def _format_params(params: dict[str, Any]) -> str:
    if not params:
        return ""
    return f"({','.join(str(value) for value in params.values())})"


def _short_output_name(func_name: str, output_name: str) -> str:
    prefix = func_name.lower()
    lower = output_name.lower()
    if lower.startswith(prefix) and len(lower) > len(prefix):
        return output_name[len(prefix) :]
    return output_name


def _last_value(array: Any) -> float | None:
    if array is None or len(array) == 0:
        return None
    value = array.iloc[-1] if hasattr(array, "iloc") else array[-1]
    if np.isnan(value):
        return None
    return float(value)


def _fmt_value(value: Any) -> str:
    number = _get_float(value)
    if number is None:
        return "nan"
    return f"{number:.6g}"


def _get_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(number) else number


def _format_timestamp(timestamp: Any) -> str:
    if isinstance(timestamp, (pd.Timestamp, datetime)):
        return timestamp.isoformat()
    return str(timestamp)
