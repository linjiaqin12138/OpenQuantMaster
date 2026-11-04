# indicator_tool

Compute arbitrary TA-Lib technical indicators and candlestick patterns from OHLCV data. Returns a summary plus an indicator-result artifact.

## Supported indicators

`indicators` accepts any TA-Lib function name (case-insensitive). The tool dispatches via `talib.abstract.Function`; there is no per-indicator special-case math path.

For backward compatibility, these six friendly aliases still map to TA-Lib functions:

| Alias | TA-Lib function | Description |
|-------|-----------------|-------------|
| `sma` | `SMA` | Simple moving average |
| `ema` | `EMA` | Exponential moving average |
| `macd` | `MACD` | Moving average convergence divergence |
| `rsi` | `RSI` | Relative strength index |
| `boll` | `BBANDS` | Bollinger bands |
| `atr` | `ATR` | Average true range |

When `indicators` is omitted, the six aliases above are computed. Unknown function names return `ToolResult(success=False)`.

## Supported candlestick patterns

`patterns` is `list[str] | None`, default `None` (no pattern detection). When a list is provided, all 61 TA-Lib `CDL*` functions are available.

- Bare names are accepted and prefixed with `CDL`, e.g. `["ENGULFING", "DOJI"]` equals `["CDLENGULFING", "CDLDOJI"]`.
- Full names such as `"CDLENGULFING"` are also accepted.
- Direction follows the TA-Lib return sign by default: `>0` → `bullish`, `<0` → `bearish`.
- Patterns that are non-zero but semantically neutral (`DOJI`, `LONGLEGGEDDOJI`, `SPINNINGTOP`, `HIKKAKE`, …) are labeled `neutral`.

## Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| source | string | no | `"symbol"` | Data source: `"symbol"` or `"ohlcv_artifact"` |
| symbol | string | conditional | `null` | Instrument code; required when `source="symbol"` |
| market | string | no | `"crypto"` | `"crypto"`, `"us_equity"`, `"hk_equity"`, or `"a_share"` |
| interval | string | no | `"1h"` | Candle interval |
| limit | integer | no | `100` | Number of candles requested; must be ≥ 1 |
| indicators | list[string] | no | `["sma", "ema", "macd", "rsi", "boll", "atr"]` | Indicator function names / aliases |
| indicator_params | dict[str, dict] | no | `{}` | Per-function (or alias) overrides of TA-Lib defaults, e.g. `{"SMA": {"timeperiod": 20}}` |
| patterns | list[string] | no | `None` | Pattern bare/full names; `None` or empty skips pattern detection |
| artifact | string | conditional | `null` | OHLCV artifact path (relative or absolute); required when `source="ohlcv_artifact"` |
| pipeline_run_id | string | no | `null` | Pipeline run id used to place output artifacts |

## Output shape

On success, `ToolResult.data` looks like:

```json
{
  "symbol": "SUIUSDT",
  "interval": "1h",
  "rows": 100,
  "indicators": {
    "sma": {
      "value": 0.71626,
      "params": { "timeperiod": 30 }
    },
    "ema": {
      "value": 0.71654,
      "params": { "timeperiod": 30 }
    },
    "macd": {
      "macd": 0.00125,
      "macdsignal": 0.00089,
      "macdhist": 0.00036,
      "params": { "fastperiod": 12, "slowperiod": 26, "signalperiod": 9 }
    },
    "rsi": {
      "value": 54.65,
      "params": { "timeperiod": 14 }
    },
    "boll": {
      "upperband": 0.72306,
      "middleband": 0.71626,
      "lowerband": 0.70946,
      "params": { "timeperiod": 5 }
    },
    "atr": {
      "value": 0.00375,
      "params": { "timeperiod": 14 }
    }
  },
  "patterns": {
    "last_bullish": "ENGULFING",
    "last_bearish": "GRAVESTONEDOJI",
    "history": [
      {
        "timestamp": "2026-07-22T13:00:00+00:00",
        "pattern": "ENGULFING",
        "label": "bullish",
        "strength": 80
      }
    ]
  },
  "summary": "SUIUSDT 1h | SMA(30)=0.7163 RSI(14)=54.7 MACD.hist=0.00036 | 形态: 看涨 ENGULFING",
  "artifact": "<run_id>/indicator_tool/indicator_result.json"
}
```

Notes:

- Single-output indicators use `{"value": ..., "params": {...}}`.
- Multi-output indicators expand `output_names` (e.g. `MACD` → `macd`, `macdsignal`, `macdhist`) and attach `params`.
- Indicators that fail at runtime (e.g. `MAVP` missing required inputs) record `{"error": "..."}` while overall `success` stays `true`.
- `patterns` is `{}` when pattern detection was not enabled.

The output artifact is JSON at `artifacts/<run_id>/indicator_tool/indicator_result.json`, matching the full `data` payload.

## CLI examples

### 1. Default indicators from a symbol

```bash
python -m runtime.cli tool indicator_tool --inputs '{"symbol": "SUIUSDT", "market": "crypto", "interval": "1h", "limit": 100}'
```

### 2. Arbitrary TA-Lib indicators with param overrides

```bash
python -m runtime.cli tool indicator_tool --inputs '{"symbol": "SUIUSDT", "market": "crypto", "interval": "1h", "indicators": ["ADX", "OBV", "STOCH"], "indicator_params": {"STOCH": {"fastk_period": 14, "slowk_period": 3, "slowd_period": 3}}}'
```

### 3. Pattern detection

```bash
python -m runtime.cli tool indicator_tool --inputs '{"symbol": "SUIUSDT", "market": "crypto", "interval": "1h", "indicators": ["rsi", "macd"], "patterns": ["ENGULFING", "DOJI"]}'
```

### 4. Read from an artifact (pipeline)

```bash
python -m runtime.cli tool indicator_tool --inputs '{"source": "ohlcv_artifact", "artifact": "run-xxx/ohlcv_tool/ohlcv_SUIUSDT_1h.csv", "indicators": ["sma", "ema", "boll"], "patterns": ["HAMMER", "ENGULFING"]}'
```

> Note: `artifact` may be relative to `artifacts/` or absolute.

## Pipeline YAML example

```yaml
name: indicator_demo

trigger:
  type: manual

stages:
  - fetch_ohlcv:
      tool: ohlcv_tool
      inputs:
        symbol: SUIUSDT
        market: crypto
        interval: 1h
        limit: 100

  - compute_indicators:
      tool: indicator_tool
      inputs:
        source: ohlcv_artifact
        artifact: "$fetch_ohlcv.out.artifact"
        indicators:
          - sma
          - ema
          - macd
          - rsi
          - boll
          - atr
        indicator_params:
          SMA:
            timeperiod: 20
          RSI:
            timeperiod: 14
        patterns:
          - ENGULFING
          - DOJI
```

## Dependencies

`indicator_tool` depends on the Python `ta-lib` package (`import talib`).

- The C TA-Lib library must be installed first on Linux/macOS, then `pip install TA-Lib`.
- Some platforms ship wheels (`ta-lib-bin`, `TA-Lib-Precompiled`, etc.).
- If `ta-lib` is unavailable, indicator computation cannot run.

## Notes

1. **Data length**: at least 2 OHLCV rows are required, and the series must satisfy the max `talib.abstract.Function.lookback` of the selected indicators/patterns. `limit=200` covers most functions.
2. **Float precision**: indicator values are floats and may show tiny floating-point differences.
3. **Patterns**: direction uses the TA-Lib integer sign; `strength` is the absolute value; neutral overrides are listed above.
4. **Symbol inference**: when reading an artifact, the tool may infer `symbol` from the filename (e.g. `ohlcv_BTC-USDT.csv` → `BTC-USDT`).
5. **Defaults**: omitting `indicators` computes the six aliases; omitting `patterns` skips pattern detection.
