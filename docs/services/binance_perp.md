# BinancePerp

Trade Binance USDT-M perpetual futures: balance / positions / open orders, plus create/cancel orders and set leverage, margin mode, and position mode.

## Config (`BinancePerpConfig`)

Injected at construction: `BinancePerp(cfg)`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exchange` | str | `binance` | Logical exchange |
| `product` | `spot` \| `usdm` | `usdm` | Product (perp uses `usdm`) |
| `sandbox` | bool | `true` | Sandbox / testnet when supported |
| `api_key` / `secret` | str | `""` | Credentials |

Exchange adapter details stay inside the service.

## Actions

| action | Kind | Notes |
|--------|------|--------|
| `balance` | read | Non-zero assets only |
| `positions` | read | `symbol` optional |
| `open_orders` | read | Resting + conditional/algo by default; see below |
| `create_order` | write | See order types |
| `cancel_order` | write | Requires `order_id` + `symbol` |
| `set_leverage` | write | Requires `leverage` + `symbol` |
| `set_margin_mode` | write | Requires `margin_mode` + `symbol` |
| `set_position_mode` | write | Requires `hedge` (`true`=hedge, `false`=one-way) |

Write actions default to `dry_run: true` and return `planned` only (no exchange client).

## Order types (`create_order`)

| order_type | Extra required fields |
|------------|----------------------|
| `market` | `amount` (unless `close_position=true`) |
| `limit` | `amount` + `price` |
| `stop_market` / `take_profit_market` | `amount` + `stop_price` |
| `stop` / `take_profit` | `amount` + `stop_price` + `price` |
| `trailing_stop_market` | `amount` + `callback_rate` (`activation_price` optional) |

Optional: `reduce_only`, `close_position`, `position_side` (`BOTH`/`LONG`/`SHORT`), `working_type` (`CONTRACT_PRICE`/`MARK_PRICE`).

## Open orders & conditionals

`open_orders` fetches resting orders, then (unless `include_conditional=false`) also algo/conditional stops. Trimmed rows include `order_kind` (`resting` \| `conditional`) and preserve venue stop types when present.

## Output (`BinancePerpOutput`)

| Field | Description |
|-------|-------------|
| `action` / `dry_run` | Echo |
| `exchange` / `product` / `sandbox` | From config |
| `planned` | Write preview when `dry_run` |
| `result` | Exchange payload (trimmed) when executed |

## Example

```python
from src.services.binance_perp import BinancePerp, BinancePerpConfig

svc = BinancePerp(BinancePerpConfig(sandbox=True, api_key="...", secret="..."))

# dry-run create
await svc.run(
    {
        "action": "create_order",
        "symbol": "BTC/USDT:USDT",
        "side": "buy",
        "order_type": "market",
        "amount": 0.001,
    }
)

# live balance
await svc.run({"action": "balance", "dry_run": False})
```

Symbol format follows the exchange adapter (e.g. `BTC/USDT:USDT` for USDM).
