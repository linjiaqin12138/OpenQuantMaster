# BinancePerp

Trade Binance USDT-M perpetual futures: balance / positions / open orders, plus create/cancel orders and set leverage, margin mode, and position mode.

Each operation is its own UseCase and its own named method on the service.

## Methods

| Method | UseCase | Request | Response |
|--------|---------|---------|----------|
| `balance()` | `FetchBalanceUseCase` | `FetchBalanceInput` | `FetchBalanceOutput` |
| `positions()` | `FetchPositionsUseCase` | `FetchPositionsInput` | `FetchPositionsOutput` |
| `open_orders()` | `FetchOpenOrdersUseCase` | `FetchOpenOrdersInput` | `FetchOpenOrdersOutput` |
| `create_order()` | `CreateOrderUseCase` | `CreateOrderInput` | `CreateOrderOutput` |
| `cancel_order()` | `CancelOrderUseCase` | `CancelOrderInput` | `CancelOrderOutput` |
| `set_leverage()` | `SetLeverageUseCase` | `SetLeverageInput` | `SetLeverageOutput` |
| `set_margin_mode()` | `SetMarginModeUseCase` | `SetMarginModeInput` | `SetMarginModeOutput` |
| `set_position_mode()` | `SetPositionModeUseCase` | `SetPositionModeInput` | `SetPositionModeOutput` |

Write actions (`create_order`, `cancel_order`, `set_leverage`, `set_margin_mode`, `set_position_mode`) default to `dry_run: true` and return `planned` only (no exchange client).

## Config (`BinancePerpServiceConfig`)

Injected at construction: `BinancePerp(cfg)`.

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `exchange` | str | `binance` | Logical exchange |
| `product` | `spot` \| `usdm` | `usdm` | Product (perp uses `usdm`) |
| `sandbox` | bool | `false` | Legacy sandbox mode; Binance USD-M testnet is no longer supported by CCXT |
| `api_key` / `secret` | str | `""` | Credentials |

The service converts its own config into the config of its UseCases (`BinancePerpUseCaseConfig`, owned by `use_cases/binance_perp.py`). Exchange adapter details stay inside the provider. The composition boundary reads the external configuration and constructs the service config: `build_binance_perp_service(app_config)`.

## Requests

The request and response models belong to the UseCases that own the actions; the service re-exports them as part of its public facade.

| Operation | Required fields | Optional fields |
|-----------|-----------------|-----------------|
| `positions` | — | `symbol` |
| `open_orders` | `symbol` | `include_conditional` (default `true`) |
| `create_order` | `symbol`, `side`, `order_type`, `amount` (unless `close_position=true`) | `price`, `stop_price`, `callback_rate`, `activation_price`, `reduce_only`, `close_position`, `position_side`, `working_type`, `dry_run` |
| `cancel_order` | `order_id`, `symbol` | `dry_run` |
| `set_leverage` | `leverage`, `symbol` | `dry_run` |
| `set_margin_mode` | `margin_mode`, `symbol` | `dry_run` |
| `set_position_mode` | `hedge` (`true`=hedge, `false`=one-way) | `dry_run` |

Order types and their extra requirements:

| order_type | Extra required fields |
|------------|----------------------|
| `market` | `amount` (unless `close_position=true`) |
| `limit` | `amount` + `price` |
| `stop_market` / `take_profit_market` | `amount` + `stop_price` |
| `stop` / `take_profit` | `amount` + `stop_price` + `price` |
| `trailing_stop_market` | `amount` + `callback_rate` (`activation_price` optional) |

`position_side` accepts `BOTH`/`LONG`/`SHORT`; `working_type` accepts `CONTRACT_PRICE`/`MARK_PRICE`.

## Responses

`FetchBalanceOutput` carries `assets` and `info_keys`; `FetchPositionsOutput` carries `positions`; `FetchOpenOrdersOutput` carries `orders` (resting + conditional/algo by default, each tagged with `order_kind`).

Write responses carry `dry_run`, `planned` (the preview) and `order` or `result` (the exchange payload when executed).

## Errors

| Code | Meaning |
|------|---------|
| `invalid_input` | The request does not satisfy the operation's request model (for example a missing `stop_price`) |
| `order_rejected` | The exchange rejected the order or the credentials |
| `exchange_unavailable` | The exchange timed out, is unreachable, or rate-limited |
| `exchange_failed` | Any other exchange failure |

## Example

```python
from src.services.binance_perp import BinancePerp, BinancePerpServiceConfig

svc = BinancePerp(
    BinancePerpServiceConfig(product="usdm", sandbox=True, api_key="...", secret="...")
)

# dry-run create
await svc.create_order(
    {
        "symbol": "BTC/USDT:USDT",
        "side": "buy",
        "order_type": "market",
        "amount": 0.001,
    }
)

# live balance
await svc.balance()
```

Symbol format follows the exchange adapter (e.g. `BTC/USDT:USDT` for USDM).
