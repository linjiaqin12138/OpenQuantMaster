# Services

Application services live under `src/services/`. Each service has explicit Pydantic config / input / output models and returns a `ServiceResult`.

| Service | Module | Doc |
|---------|--------|-----|
| `OHLCV` | `src.services.ohlcv` | [ohlcv.md](./ohlcv.md) |
| `Indicator` | `src.services.indicator` | [indicator.md](./indicator.md) |
| `BinancePerp` | `src.services.binance_perp` | [binance_perp.md](./binance_perp.md) |

Call pattern:

```python
result = await Service(cfg).run({...})  # dict → validated input model
# result.success / result.data / result.error  # ServiceError(code, message, exception: Exception | None)
```
