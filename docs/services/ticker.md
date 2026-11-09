# Ticker

Fetch the latest point-in-time snapshot for an A-share stock, index, listed ETF, or crypto symbol. This complements OHLCV history; it is not a streaming subscription or an exchange-grade real-time feed.

## Method

`await service.fetch_ticker(request)` — one operation, one UseCase (`FetchTickerUseCase`).

## Config (`TickerServiceConfig`)

Injected at construction: `Ticker(cfg)`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `tushare_token` | str | `""` | Tushare token; required for `a_share` |
| `exchange` | str | `binance` | Logical exchange for crypto |
| `product` | `spot` \| `usdm` | `spot` | Crypto product on that exchange |
| `sandbox` | bool | `false` | Sandbox / testnet when supported |
| `api_key` | str | `""` | Optional API key |
| `secret` | str | `""` | Optional API secret |

The composition boundary reads the existing external `providers.tushare.token` and `providers.binance` sections and constructs the service with `build_ticker_service(app_config)`. No additional provider configuration is required.

## Request (`FetchTickerInput`)

| Field | Required | Description |
|-------|----------|-------------|
| `symbol` | yes | A-share code such as `600519.SH` or `515070`; crypto symbol such as `BTC/USDT` or `BTC/USDT:USDT` |
| `market` | yes | `a_share` or `crypto` |

### A-share symbols without a suffix

A code prefix never decides the exchange on its own: `9` covers both the Shanghai B shares and the Beijing codes, and `1` covers both Shenzhen funds and Shanghai convertible bonds. The service therefore treats the suffix as a query order, not as an answer:

1. Every plausible exchange for the code is queried, ordered by prefix likelihood (`5`/`6` Shanghai first, `4`/`8`/`9` Beijing first, otherwise Shenzhen first).
2. Exactly one listing must answer. That listing is returned, and `symbol` reports the resolved code, for example `000300` resolves to `000300.SH`.
3. Two listings answering the same code is an ambiguity, not a guess: the request fails with `ambiguous_symbol` and names both candidates, for example `000001.SZ` (平安银行) and `000001.SH` (上证指数). Callers resolve it by sending the explicit suffix.
4. No listing answering is `market_data_failed`. Some instruments, such as Beijing-listed codes, are not covered by the quote source and therefore report as not found.

Supplying the explicit suffix costs one provider call instead of two or three and removes the ambiguity risk, so it is the preferred form.

Crypto symbols use the configured venue. A perpetual symbol such as `BTC/USDT:USDT` always selects the USDT-M venue, because the symbol carries the `:USDT` settlement suffix.

## Response (`FetchTickerOutput` in `ServiceResult.data`)

| Field | Description |
|-------|-------------|
| `symbol` / `market` | Request echo; `symbol` is the resolved A-share code when a suffix was derived |
| `name` | Instrument name from the provider |
| `source` | `tushare` or `ccxt` |
| `price` | Latest snapshot price |
| `previous_close` | Previous close, or `null` when the venue does not report one |
| `open` / `high` / `low` | Session prices, or `null` when unavailable |
| `change` / `change_percent` | Absolute and percentage change, or `null` when unavailable |
| `bid` / `ask` | Best bid and ask, `null` for sources that do not report them |
| `quote_time` | Provider quote timestamp as an ISO-8601 UTC string, `null` when the venue reports no timestamp |
| `fetched_at` | Local fetch timestamp as an ISO-8601 UTC string |

`quote_time` and `fetched_at` have different meanings. Callers must use `quote_time` when assessing quote freshness and must not describe `fetched_at` as the exchange quote time.

## Errors

| Code | Meaning |
|------|---------|
| `invalid_input` | The symbol or market does not satisfy `FetchTickerInput` |
| `ambiguous_symbol` | The code is listed on more than one exchange; the suffix is required |
| `missing_provider_token` | No Tushare token is configured for an A-share request |
| `market_data_unavailable` | The provider timed out, is unreachable, or rate-limited |
| `market_data_rejected` | The provider rejected the request, token, or permission |
| `market_data_failed` | Any other provider or snapshot-validation failure, including a code the source does not cover |

## Example

```python
from src.services.ticker import Ticker, TickerServiceConfig

svc = Ticker(TickerServiceConfig(tushare_token="your-token"))
result = await svc.fetch_ticker({"symbol": "000300", "market": "a_share"})
assert result.success
print(result.data["symbol"], result.data["price"], result.data["quote_time"])
```
