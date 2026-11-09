# Services

Application services live under `src/services/`. Each service is the public facade of one capability: it groups the UseCases of that capability and exposes them through semantically named methods.

A service owns its configuration and only delegates through semantically named methods. Each UseCase owns its Config, Input, and Output models; the Service imports and reuses those operation models rather than defining duplicates. `BaseUseCase.run()` owns model validation, execution, result normalization, and timing; Service/BaseService must not duplicate them through a generic `_execute()` helper. The layers below it are `src/use_cases/` (the workflow, the provider calls, and the error-code mapping) and `src/providers/` (the stateless third-party calls).

| Service | Capability | Methods |
|---------|------------|---------|
| `OHLCV` | market data | `fetch_bars()` |
| `Indicator` | technical analysis | `compute()` |
| `NewsFetcher` | news | `fetch_recent()`, `fetch_stock_news()` |
| `NotificationService` | notification | `send()` |
| `BinancePerp` | perpetual futures | `balance()`, `positions()`, `open_orders()`, `create_order()`, `cancel_order()`, `set_leverage()`, `set_margin_mode()`, `set_position_mode()` |

### Call pattern

```python
result = await service.fetch_bars({"symbol": "BTCUSDT", "market": "crypto", "interval": "1h"})
# result.success / result.data / result.error  # Error(code, message, exception: Exception | None)
```

Each Service method accepts its UseCase's request model or a plain dict and delegates directly to `UseCase.run()`. The UseCase boundary validates the dict against its Input model and returns a `ServiceResult` whose successful `data` is validated and serialized from its Output model, so protocols can render or serialize it directly.

### Configuration ownership

| Level | Owner | Example |
|-------|-------|---------|
| External format | `src/config.py` | `AppConfig`, `providers.binance`, `providers.pushplus` |
| Capability | `src/services/<capability>.py` | `OHLCVServiceConfig` |
| Action | `src/use_cases/<capability>.py` | `FetchBarsUseCaseConfig`, `FetchBarsInput`, `FetchBarsOutput` |

`src/config.py` owns only the external configuration format and its loading. Each Service owns its Config class, accepts it in its constructor, and explicitly converts its fields into the Config of each UseCase it constructs. Each UseCase owns its Config class and its request/response models. `src/composition.py` is the composition boundary: it reads the external configuration, builds the Service Configs, and calls the Service constructors.
