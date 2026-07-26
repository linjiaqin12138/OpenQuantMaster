from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
import structlog
import talib
import talib.abstract as ta
from pydantic import BaseModel, Field, model_validator

from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult

logger = structlog.get_logger()

# Friendly aliases for the six default indicators.  Computation still goes through
# talib.abstract.Function like any other function name.
INDICATOR_ALIASES = {
    "sma": "SMA",
    "ema": "EMA",
    "macd": "MACD",
    "rsi": "RSI",
    "boll": "BBANDS",
    "atr": "ATR",
}

# Patterns whose TA-Lib value is non-zero but should be labelled neutral.
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


class IndicatorToolInput(BaseModel):
    source: Literal["ohlcv_artifact", "symbol"] = "symbol"
    artifact: str | None = None
    symbol: str | None = None
    market: Literal["crypto", "us_equity", "hk_equity", "a_share"] = "crypto"
    interval: str = "1h"
    limit: int = Field(default=100, ge=1)
    indicators: list[str] = Field(
        default_factory=lambda: ["sma", "ema", "macd", "rsi", "boll", "atr"]
    )
    indicator_params: dict[str, dict] = Field(default_factory=dict)
    patterns: list[str] | None = Field(default=None)
    pipeline_run_id: str | None = None

    @model_validator(mode="after")
    def check_source_consistency(self) -> "IndicatorToolInput":
        if self.source == "ohlcv_artifact" and not self.artifact:
            raise ValueError("artifact is required when source='ohlcv_artifact'")
        if self.source == "symbol" and not self.symbol:
            raise ValueError("symbol is required when source='symbol'")
        return self


class IndicatorToolOutput(BaseModel):
    symbol: str
    interval: str
    rows: int
    indicators: dict[str, Any]
    patterns: dict[str, Any]
    summary: str
    artifact: str


class IndicatorTool(BaseTool):
    name: ClassVar[str] = "indicator_tool"
    version: ClassVar[str] = "0.2.0"
    capability: ClassVar[str] = "market_data"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = IndicatorToolInput
    output_model: ClassVar[type[BaseModel]] = IndicatorToolOutput

    def __init__(self, artifacts_path: Path | str | None = None) -> None:
        self._artifacts_path: Path | None = Path(artifacts_path) if artifacts_path else None

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        validated = self.input_model(**inputs)
        inputs = validated.model_dump()

        run_id = inputs.get("pipeline_run_id") or str(uuid.uuid4())

        cfg = self._load_config()
        artifacts_path = self._artifacts_path or cfg.paths.artifacts

        indicators = inputs["indicators"]
        indicator_func_names = [_resolve_indicator_name(n) for n in indicators]
        valid_funcs = set(talib.get_functions())
        for name, func_name in zip(indicators, indicator_func_names):
            if func_name not in valid_funcs:
                return ToolResult(
                    success=False,
                    error=f"Unknown indicator function: {name}",
                )

        source = inputs["source"]
        if source == "ohlcv_artifact":
            df = self._load_ohlcv_from_artifact(str(inputs["artifact"]), artifacts_path)
            symbol = _guess_symbol_from_path(str(inputs["artifact"]))
        else:
            symbol = str(inputs["symbol"])
            market = inputs.get("market", "crypto")
            interval = inputs.get("interval", "1h")
            limit = inputs.get("limit", 100)
            df = await self._load_ohlcv_from_symbol(
                symbol, market, interval, limit
            )

        interval = inputs.get("interval", "1h")
        rows = len(df)
        if rows < 2:
            return ToolResult(success=False, error="OHLCV data requires at least 2 rows")

        indicator_params = {
            _resolve_indicator_name(k): v
            for k, v in inputs.get("indicator_params", {}).items()
        }
        patterns = inputs.get("patterns") or []

        required_min_period = self._compute_required_min_period(
            indicator_func_names, patterns, indicator_params, df
        )
        if rows < required_min_period:
            return ToolResult(
                success=False,
                error=f"Insufficient data: {rows} rows provided, "
                f"but at least {required_min_period} rows are required "
                f"for the configured indicators/patterns",
            )

        computed_indicators = self._compute_indicators(
            df, indicators, indicator_func_names, indicator_params
        )
        computed_patterns = self._compute_patterns(df, patterns)

        summary = self._build_summary(
            symbol, interval, computed_indicators, computed_patterns
        )

        payload = {
            "symbol": symbol,
            "interval": interval,
            "rows": rows,
            "indicators": computed_indicators,
            "patterns": computed_patterns,
            "summary": summary,
        }

        artifact_dir = artifacts_path / run_id / "indicator_tool"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "indicator_result.json"
        content = json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default)
        artifact_path.write_text(content, encoding="utf-8")

        relative_path = str(artifact_path.relative_to(artifacts_path))
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        artifact = ArtifactRef(
            name="indicator_result.json",
            mime_type="application/json",
            relative_path=relative_path,
            sha256=sha256,
            content=content,
        )

        output = self.output_model(
            symbol=symbol,
            interval=interval,
            rows=rows,
            indicators=computed_indicators,
            patterns=computed_patterns,
            summary=summary,
            artifact=relative_path,
        )
        return ToolResult(success=True, data=output.model_dump(), artifacts=[artifact])

    def _load_config(self) -> Any:
        from runtime.config_loader import load_config

        try:
            return load_config()
        except FileNotFoundError:
            from runtime.config_loader import RuntimeConfig

            return RuntimeConfig()

    def _load_ohlcv_from_artifact(
        self, artifact: str, artifacts_path: Path
    ) -> pd.DataFrame:
        artifact_path = Path(artifact)
        if not artifact_path.is_absolute():
            artifact_path = artifacts_path / artifact
        if not artifact_path.exists():
            raise FileNotFoundError(f"OHLCV artifact not found: {artifact_path}")
        df = pd.read_csv(artifact_path)
        return self._normalize_ohlcv(df)

    async def _load_ohlcv_from_symbol(
        self,
        symbol: str,
        market: str,
        interval: str,
        limit: int,
    ) -> pd.DataFrame:
        from tools.market_data.ohlcv_tool import OHLCVTool

        tool = OHLCVTool()
        result = await tool.execute(
            {
                "symbol": symbol,
                "market": market,
                "interval": interval,
                "limit": limit,
            }
        )
        if not result.success or not result.artifacts:
            error = result.error or "ohlcv_tool returned no data"
            raise RuntimeError(f"Failed to fetch OHLCV data: {error}")

        csv_content = result.artifacts[0].content
        if csv_content is None:
            raise RuntimeError("OHLCV artifact has no content")

        from io import StringIO

        df = pd.read_csv(StringIO(csv_content))
        return self._normalize_ohlcv(df)

    def _normalize_ohlcv(self, df: pd.DataFrame) -> pd.DataFrame:
        expected = ["timestamp", "open", "high", "low", "close", "volume"]
        missing = [c for c in expected if c not in df.columns]
        if missing:
            raise ValueError(f"OHLCV CSV missing columns: {missing}")
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
                    indicator_parts.append(
                        f"{display_name}.{short_name}={value_str}"
                    )

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


def _guess_symbol_from_path(path: str) -> str:
    stem = Path(path).stem
    if stem.startswith("ohlcv_"):
        return stem.replace("ohlcv_", "", 1)
    return stem


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer, np.floating)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
