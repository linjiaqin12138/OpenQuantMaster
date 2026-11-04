# Indicator

Compute TA-Lib indicators and candlestick patterns from OHLCV bars. Returns summary + structured values in `ServiceResult.data` (no artifacts).

## Construction

```python
Indicator()                 # bars required in input
Indicator(ohlcv=ohlcv_svc)  # bars or symbol (symbol path uses OHLCV)
```

`input_model` is chosen in `__init__`: without `ohlcv`, `bars` is required; with `ohlcv`, provide `bars` or `symbol`.

## Input

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `bars` | conditional | `null` | OHLCV bar list (`timestamp/open/high/low/close/volume`) |
| `symbol` | conditional | `null` | Required when fetching via injected `OHLCV` |
| `market` | no | `crypto` | Passed to OHLCV when fetching |
| `interval` | no | `1h` | Candle interval |
| `limit` | no | `100` | Bars requested when fetching by symbol |
| `indicators` | no | six aliases | TA-Lib names or aliases |
| `indicator_params` | no | `{}` | Per-function overrides, e.g. `{"SMA": {"timeperiod": 20}}` |
| `patterns` | no | `null` | Candlestick pattern names; omit to skip |

### Indicator aliases

| Alias | TA-Lib |
|-------|--------|
| `sma` | `SMA` |
| `ema` | `EMA` |
| `macd` | `MACD` |
| `rsi` | `RSI` |
| `boll` | `BBANDS` |
| `atr` | `ATR` |

Any other TA-Lib function name is accepted (case-insensitive). Unknown names fail the call.

### Patterns

Bare names are prefixed with `CDL` (e.g. `ENGULFING` → `CDLENGULFING`). Sign of the TA-Lib value maps to `bullish` / `bearish`; a fixed set of neutral patterns is labeled `neutral`.

## Output (`IndicatorOutput`)

| Field | Description |
|-------|-------------|
| `symbol` / `interval` / `rows` | Series metadata |
| `indicators` | Per-name values + params (or `{"error": "..."}`) |
| `patterns` | `last_bullish`, `last_bearish`, `history` (or `{}` if disabled) |
| `summary` | Short human-readable line |

## Example

```python
from src.services.indicator import Indicator

result = await Indicator().run(
    {
        "symbol": "BTCUSDT",
        "interval": "1h",
        "bars": bars,  # from OHLCV.data["bars"]
        "indicators": ["sma", "rsi", "macd"],
        "patterns": ["ENGULFING", "DOJI"],
    }
)
```

## Dependencies

Requires the Python `ta-lib` package (system C library + wheel/install as usual).

## Notes

- Need at least 2 bars, and enough rows for the max TA-Lib lookback of selected functions.
- Per-indicator runtime errors are stored under that name; overall `success` can still be `true`.
