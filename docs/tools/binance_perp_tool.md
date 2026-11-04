# binance_perp_tool

Trade Binance USDT-M perpetual futures via CCXT (default `binanceusdm`): balance / positions / open orders, plus create/cancel orders and set leverage, margin mode, and position mode.

Credentials and connection settings come from top-level `exchanges.binance`, resolved through `execution.binance_perp` (`exchange` + `product`, default `binance` / `usdm`). Write actions default to `dry_run: true` and return `planned` only—no exchange write calls.

## Supported actions

| action | Kind | Notes |
|--------|------|--------|
| `balance` | read | Account balance (non-zero assets only) |
| `positions` | read | Open positions; `symbol` optional |
| `open_orders` | read | Open orders (resting + conditional/algo by default); `symbol` optional; see [Open orders & conditionals](#open-orders--conditionals) |
| `create_order` | write | Place an order (see order types below) |
| `cancel_order` | write | Cancel; requires `order_id` + `symbol` |
| `set_leverage` | write | Set leverage; requires `leverage` + `symbol` |
| `set_margin_mode` | write | Set margin mode; requires `margin_mode` + `symbol` |
| `set_position_mode` | write | Set position mode; requires `hedge` (`true`=hedge, `false`=one-way) |

Write actions: `create_order`, `cancel_order`, `set_leverage`, `set_margin_mode`, `set_position_mode`. When `dry_run=true` (default), the tool does not instantiate an exchange client and returns `planned` only.

## Order types (`create_order`)

| order_type | Extra required fields | Notes |
|------------|----------------------|--------|
| `market` | `amount` (unless `close_position=true`) | Market order |
| `limit` | `amount` + `price` | Limit order |
| `stop_market` | `amount` + `stop_price` | Stop-market |
| `take_profit_market` | `amount` + `stop_price` | Take-profit market |
| `stop` | `amount` + `stop_price` + `price` | Stop-limit |
| `take_profit` | `amount` + `stop_price` + `price` | Take-profit limit |
| `trailing_stop_market` | `amount` + `callback_rate` | Trailing stop; `activation_price` optional |

Optional order params:

- `reduce_only` — reduce-only
- `close_position` — close position (`amount` may be omitted)
- `position_side` — `BOTH` / `LONG` / `SHORT` (common in hedge mode)
- `working_type` — `CONTRACT_PRICE` / `MARK_PRICE` (conditional trigger price type)

## Inputs

| Name | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| action | string | yes | — | See actions table |
| dry_run | bool | no | `true` | Preview write actions; read actions always hit the exchange |
| symbol | string | conditional | `null` | CCXT symbol, e.g. `BTC/USDT:USDT`; required for `create_order` / `cancel_order` / `set_leverage` / `set_margin_mode`; optional for `positions` / `open_orders` |
| side | string | conditional | `null` | `buy` / `sell`; required for `create_order` |
| order_type | string | conditional | `null` | See order types; required for `create_order` |
| amount | float | conditional | `null` | Size, must be `>0`; required for `create_order` unless `close_position` |
| price | float | conditional | `null` | Limit price, must be `>0`; required for `limit` / `stop` / `take_profit` |
| stop_price | float | conditional | `null` | Trigger price, must be `>0`; required for conditional stops |
| callback_rate | float | conditional | `null` | Trailing callback rate `0.1`–`10`; required for `trailing_stop_market` |
| activation_price | float | no | `null` | Trailing activation price, must be `>0` |
| order_id | string | conditional | `null` | Required for `cancel_order` |
| leverage | int | conditional | `null` | `1`–`125`; required for `set_leverage` |
| margin_mode | string | conditional | `null` | `isolated` / `cross`; required for `set_margin_mode` |
| reduce_only | bool | no | `false` | Reduce-only |
| close_position | bool | no | `false` | Close position; when `true`, `amount` may be omitted |
| position_side | string | no | `null` | `BOTH` / `LONG` / `SHORT` |
| working_type | string | no | `null` | `CONTRACT_PRICE` / `MARK_PRICE` |
| hedge | bool | conditional | `null` | Required for `set_position_mode`; `true`=hedge, `false`=one-way |
| include_conditional | bool | no | `true` | `open_orders` only: also fetch Binance algo/conditional orders (TP/SL). Set `false` for resting book only |

Validation failures return `ToolResult(success=False)` with the reason in `error` (e.g. missing `stop_price`).

## Output shape

On success, `ToolResult.data` looks like:

```json
{
  "action": "balance",
  "dry_run": true,
  "exchange": "binance",
  "product": "usdm",
  "ccxt_id": "binanceusdm",
  "sandbox": true,
  "planned": null,
  "result": {
    "assets": {
      "USDT": { "free": 1000.0, "used": 0.0, "total": 1000.0 }
    },
    "info_keys": []
  }
}
```

Notes:

- Write action with `dry_run=true`: `planned` is the intended params dict; `result` is `null`.
- Live execution (reads, or writes with `dry_run=false`): `planned` is `null`; `result` is a trimmed exchange payload.
- `exchange` / `product` / `ccxt_id` / `sandbox` come from config resolution so you can confirm which venue you hit.

### dry_run `planned` example

```json
{
  "action": "create_order",
  "dry_run": true,
  "exchange": "binance",
  "product": "usdm",
  "ccxt_id": "binanceusdm",
  "sandbox": true,
  "planned": {
    "action": "create_order",
    "symbol": "BTC/USDT:USDT",
    "side": "sell",
    "order_type": "stop_market",
    "amount": 0.001,
    "stop_price": 45000.0,
    "reduce_only": true,
    "position_side": "LONG"
  },
  "result": null
}
```

### Trimmed `result` fields

| Object | Fields kept |
|--------|-------------|
| balance | `assets.<coin>.{free,used,total}`, `info_keys` (non-zero assets only) |
| position | `symbol`, `side`, `contracts`, `contractSize`, `entryPrice`, `markPrice`, `notional`, `leverage`, `unrealizedPnl`, `marginMode`, `hedged`, `percentage` |
| order | `id`, `clientOrderId`, `symbol`, `order_kind`, `type`, `side`, `price`, `amount`, `filled`, `remaining`, `status`, `reduceOnly`, `stopPrice`, `workingType`, `algoStatus`, `closePosition`, `timestamp` |

`set_leverage` / `set_margin_mode` / `set_position_mode` pass through the CCXT return value as `result`.

This tool does not write artifact files; results are returned only in `ToolResult.data`.

## Open orders & conditionals

Binance USDM keeps **resting** orders (e.g. limits) and **conditional / algo** orders (stop-loss, take-profit, OTOCO legs) on different endpoints. Plain `fetch_open_orders(symbol)` returns only the resting book; TP/SL require `params={"stop": true}` (CCXT → open algo orders).

`open_orders` therefore:

1. Fetches resting orders.
2. Unless `include_conditional=false`, also fetches conditional/algo orders.
3. Returns **one list** (`result: [...]`) with resting first, then conditional.

### How to tell them apart

| Field | Resting | Conditional (TP/SL) |
|-------|---------|---------------------|
| `order_kind` | `"resting"` | `"conditional"` |
| `type` | CCXT type (`limit`, `market`, …) | Venue `info.orderType` lowercased (`stop_market`, `take_profit_market`, …) — **not** CCXT’s normalized `"market"` |
| `stopPrice` | usually `null` | trigger price |
| `workingType` | `null` | `CONTRACT_PRICE` / `MARK_PRICE` |
| `algoStatus` | `null` | e.g. `NEW` |
| `closePosition` | often `null`/`false` | bool from algo payload |
| `id` | exchange order id | algo id (`algoId`) |

Do **not** rely on `type === "market"` to detect stops: CCXT maps many conditionals to `type: "market"`. Use `order_kind` + `type`.

### `open_orders` example

```json
{
  "action": "open_orders",
  "dry_run": true,
  "exchange": "binance",
  "product": "usdm",
  "ccxt_id": "binanceusdm",
  "sandbox": false,
  "planned": null,
  "result": [
    {
      "id": "99",
      "clientOrderId": "limit-1",
      "symbol": "SUI/USDT:USDT",
      "order_kind": "resting",
      "type": "limit",
      "side": "sell",
      "price": 0.9,
      "amount": 10.0,
      "filled": 0.0,
      "remaining": 10.0,
      "status": "open",
      "reduceOnly": false,
      "stopPrice": null,
      "workingType": null,
      "algoStatus": null,
      "closePosition": null,
      "timestamp": 1
    },
    {
      "id": "1000002667807070",
      "clientOrderId": "stToAg_OTOCO_1",
      "symbol": "SUI/USDT:USDT",
      "order_kind": "conditional",
      "type": "take_profit_market",
      "side": "buy",
      "price": null,
      "amount": 48.3,
      "filled": 0.0,
      "remaining": 48.3,
      "status": "open",
      "reduceOnly": true,
      "stopPrice": 0.8488,
      "workingType": "CONTRACT_PRICE",
      "algoStatus": "NEW",
      "closePosition": false,
      "timestamp": 2
    },
    {
      "id": "1000002667807071",
      "order_kind": "conditional",
      "type": "stop_market",
      "side": "buy",
      "amount": 48.3,
      "stopPrice": 0.9008,
      "workingType": "CONTRACT_PRICE",
      "algoStatus": "NEW",
      "reduceOnly": true
    }
  ]
}
```

**Cancel note:** `cancel_order` still uses the standard cancel path with `order_id`. Cancelling algo/conditional ids may require a dedicated algo cancel API; treat that as a follow-up if cancel of `order_kind=conditional` fails.

## Configuration

`config.yaml` example:

```yaml
exchanges:
  binance:
    apiKey: "YOUR_KEY"
    secret: "YOUR_SECRET"
    usdm:
      ccxt_id: binanceusdm
      sandbox: true   # true=testnet; false=mainnet — use with care

execution:
  binance_perp:
    exchange: binance
    product: usdm
```

- Product-level `apiKey` / `secret`, when set, override exchange-level credentials.
- When `sandbox: true`, the tool calls `exchange.set_sandbox_mode(True)`.
- Default `usdm.sandbox=true` to avoid accidental mainnet use.

## CLI examples

### 1. Balance

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"balance"}'
```

### 2. Positions / open orders

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"positions","symbol":"BTC/USDT:USDT"}'
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"open_orders","symbol":"BTC/USDT:USDT"}'
# resting book only (skip TP/SL algo orders)
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"open_orders","symbol":"BTC/USDT:USDT","include_conditional":false}'
```

### 3. Market entry (dry_run by default)

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"create_order","symbol":"BTC/USDT:USDT","side":"buy","order_type":"market","amount":0.001}'
```

### 4. Stop-market dry_run

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"create_order","symbol":"BTC/USDT:USDT","side":"sell","order_type":"stop_market","amount":0.001,"stop_price":45000,"reduce_only":true,"position_side":"LONG"}'
```

### 5. Live order (explicitly disable dry_run)

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"create_order","symbol":"BTC/USDT:USDT","side":"sell","order_type":"stop_market","amount":0.001,"stop_price":45000,"reduce_only":true,"dry_run":false}'
```

### 6. Cancel / leverage / margin mode / position mode

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"cancel_order","symbol":"BTC/USDT:USDT","order_id":"123456","dry_run":false}'
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"set_leverage","symbol":"BTC/USDT:USDT","leverage":5,"dry_run":false}'
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"set_margin_mode","symbol":"BTC/USDT:USDT","margin_mode":"isolated","dry_run":false}'
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"set_position_mode","hedge":true,"dry_run":false}'
```

## Pipeline YAML example

```yaml
name: binance_perp_demo

trigger:
  type: manual

stages:
  - check_balance:
      tool: binance_perp_tool
      inputs:
        action: balance

  - plan_entry:
      tool: binance_perp_tool
      inputs:
        action: create_order
        symbol: BTC/USDT:USDT
        side: buy
        order_type: market
        amount: 0.001
        # dry_run defaults to true; set false only after review
```

## Dependencies

- Python package `ccxt` (async client via `import ccxt.async_support`).
- Runtime config must resolve `exchanges.binance` + `execution.binance_perp`. Missing credentials may cause read calls to fail depending on venue/testnet rules.

## Notes

1. **dry_run defaults on**: write actions without `"dry_run": false` never hit exchange write APIs—inspect `planned` first.
2. **Reads always hit the exchange**: `balance` / `positions` / `open_orders` ignore `dry_run`.
3. **Symbol format**: use CCXT perpetual form, e.g. `BTC/USDT:USDT` (not `BTCUSDT`).
4. **Sandbox vs mainnet**: controlled by `exchanges.binance.usdm.sandbox`; confirm keys and `dry_run` before switching off sandbox.
5. **Position mode**: `set_position_mode` may be rejected with open positions/orders; hedge-mode orders often need `position_side`.
6. **Conditional orders**: `open_orders` includes algo TP/SL by default (`include_conditional=true`). Filter with `order_kind` / `type` — see [Open orders & conditionals](#open-orders--conditionals).
7. **No artifacts**: this tool does not write files; later pipeline stages should reference `$stage.out.*` fields.
