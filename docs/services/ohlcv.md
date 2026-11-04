# OHLCV

Fetch OHLCV bars for crypto, US/HK equities, or A-shares. Returns rows in `data.bars` (no artifacts).

## Config (`OHLCVConfig`)

Injected at construction: `OHLCV(cfg)`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `crypto.exchange` | str | `binance` | Logical exchange name |
| `crypto.product` | `spot` \| `usdm` | `spot` | Product on that exchange |
| `crypto.sandbox` | bool | `false` | Sandbox / testnet when supported |
| `crypto.api_key` | str | `""` | Optional API key |
| `crypto.secret` | str | `""` | Optional API secret |
| `tushare_token` | str | `""` | Used for A-share when present |

Provider adapters (e.g. CCXT class ids) stay inside the service; callers only use exchange/product.

## Input (`OHLCVInput`)

| Field | Required | Description |
|-------|----------|-------------|
| `symbol` | yes | Ticker, e.g. `BTCUSDT`, `AAPL`, `000001.SZ` |
| `market` | yes | `crypto`, `us_equity`, `hk_equity`, `a_share` |
| `interval` | yes | e.g. `1d`, `1h`, `15m` |
| `start` / `end` | no | ISO-8601 window |
| `limit` | no | Default `1000`, max `5000` |
| `source` | no | Force provider: `ccxt`, `yfinance`, `tushare`, `akshare` |

Selection:

- `crypto` (or `source=ccxt`) → crypto config venue
- `us_equity` / `hk_equity` (or `source=yfinance`) → yfinance
- `a_share` → tushare when token set, else akshare

## Output (`OHLCVOutput` in `ServiceResult.data`)

| Field | Description |
|-------|-------------|
| `symbol` / `market` / `interval` | Echo of request |
| `rows` | Number of bars |
| `bars` | List of `{timestamp, open, high, low, close, volume}` |

## Example

```python
from src.services.ohlcv import OHLCV, OHLCVConfig, OHLCVCryptoConfig

svc = OHLCV(OHLCVConfig(crypto=OHLCVCryptoConfig(exchange="binance", product="spot")))
result = await svc.run(
    {"symbol": "BTCUSDT", "market": "crypto", "interval": "1h", "limit": 100}
)
assert result.success
bars = result.data["bars"]
```
