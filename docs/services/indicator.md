# Indicator

Compute TA-Lib indicators and candlestick patterns from OHLCV bars. Returns summary + structured values in `ServiceResult.data` (no artifacts).

## Method

`await service.compute(request)` — one operation, one UseCase (`ComputeIndicatorsUseCase`), which composes the market-data UseCase when no bars are supplied.

## Construction

```python
Indicator(IndicatorServiceConfig())   # market-data settings included
build_indicator_service(app_config)                # from the external configuration
```

`IndicatorServiceConfig` holds the market-data settings (`exchange`, `product`, `sandbox`, `api_key`, `secret`, `tushare_token`); the service converts them into the config of the market-data UseCase it composes.

## Request (`ComputeIndicatorsInput`)

The request and response models belong to the UseCase that owns the action; the service re-exports them as part of its public facade.

| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `bars` | conditional | `null` | OHLCV bar list (`timestamp/open/high/low/close/volume`) |
| `symbol` | conditional | `null` | Required when fetching by symbol |
| `market` | no | `crypto` | Passed to the market-data workflow when fetching |
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

## Response (`ComputeIndicatorsOutput`)

| Field | Description |
|-------|-------------|
| `symbol` / `interval` / `rows` | Series metadata |
| `indicators` | Per-name values + params (or `{"error": "..."}`) |
| `patterns` | `last_bullish`, `last_bearish`, `history` (or `{}` if disabled) |
| `summary` | Short human-readable line |

## Errors

| Code | Meaning |
|------|---------|
| `invalid_input` | The request does not satisfy `ComputeIndicatorsInput` (for example neither `bars` nor `symbol`) |
| `unknown_indicator` | The requested TA-Lib function does not exist |
| `insufficient_data` | Fewer rows than the longest lookback of the selected functions |
| `market_data_*` | The market-data workflow failed while fetching by symbol |

## Example

```python
from src.services.indicator import Indicator, IndicatorServiceConfig

result = await Indicator(IndicatorServiceConfig()).compute(
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
