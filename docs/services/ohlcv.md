# OHLCV

Fetch OHLCV bars for crypto, US/HK equities, or A-shares. Returns rows in `data.bars` (no artifacts). OHLCV provides historical bar context, not a latest-quote snapshot; use [Ticker](ticker.md) for current A-share prices with a provider quote timestamp.

## Method

`await service.fetch_bars(request)` — one operation, one UseCase (`FetchBarsUseCase`).

## Config (`OHLCVServiceConfig`)

Injected at construction: `OHLCV(cfg)`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exchange` | str | `binance` | Logical exchange name |
| `product` | `spot` \| `usdm` | `spot` | Product on that exchange |
| `sandbox` | bool | `false` | Sandbox / testnet when supported |
| `api_key` | str | `""` | Optional API key |
| `secret` | str | `""` | Optional API secret |
| `tushare_token` | str | `""` | Used for A-share when present |

The service converts its own config into the config of its UseCase (`FetchBarsUseCaseConfig`, owned by `use_cases/ohlcv.py`). Provider adapters (e.g. CCXT class ids) stay inside the provider; callers only use exchange/product.

The composition boundary reads the external configuration and constructs the service config: `build_ohlcv_service(app_config)`.

## Request (`FetchBarsInput`)

The request and response models belong to the UseCase that owns the action; the service re-exports them as part of its public facade.

| Field | Required | Description |
|-------|----------|-------------|
| `symbol` | yes | Ticker, e.g. `BTCUSDT`, `AAPL`, `000001.SZ` |
| `market` | yes | `crypto`, `us_equity`, `hk_equity`, `a_share` |
| `interval` | yes | e.g. `1d`, `1h`, `15m` |
| `start` / `end` | no | ISO-8601 window |
| `limit` | no | Default `1000`, max `5000` |
| `source` | no | Force provider: `ccxt`, `yfinance`, `tushare`, `akshare` |

Selection:

- `crypto` → CCXT
- `us_equity` / `hk_equity` → yfinance
- `a_share` → Tushare when a token is set, else AkShare; a Tushare failure falls back to AkShare unless `source=tushare` is explicit
- an explicit `source` must match the market, otherwise the request fails with `unsupported_source`

## Response (`FetchBarsOutput` in `ServiceResult.data`)

| Field | Description |
|-------|-------------|
| `symbol` / `market` / `interval` | Echo of request |
| `rows` | Number of bars |
| `bars` | List of `{timestamp, open, high, low, close, volume}`; `timestamp` is an ISO-8601 UTC string |

## Errors

| Code | Meaning |
|------|---------|
| `invalid_input` | The request does not satisfy `FetchBarsInput` |
| `unsupported_source` | The requested source does not serve the requested market |
| `market_data_unavailable` | The provider timed out, is unreachable, or rate-limited |
| `market_data_rejected` | The provider rejected the request or the credentials |
| `market_data_failed` | Any other provider failure |

## Example

```python
from src.services.ohlcv import OHLCV, OHLCVServiceConfig

svc = OHLCV(OHLCVServiceConfig(exchange="binance", product="spot"))
result = await svc.fetch_bars(
    {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h", "limit": 100}
)
assert result.success
bars = result.data["bars"]
```
