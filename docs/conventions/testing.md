# Testing conventions

## Goals

Tests should survive internal refactors. Prefer stable **public surfaces** — **Service** APIs (`BaseService.run` with documented Pydantic config / input / output) and external SDK APIs — over private helpers.

## Prefer entrypoints

- Drive behavior through a **Service**: construct with its config (or dependencies), then `await service.run({...})`.
- **Operation** unit tests may call a single atomic Operation directly when asserting pure logic or one I/O boundary; do not use that shortcut for multi-step workflows (those belong under Service tests).
- Assert on `ServiceResult` (`success`, `data`, `error` as `ServiceError | None` with `code` / `message` / `exception`) and documented output fields. Do not assert on private helpers or internal return types unless they are part of a published contract.
- Internal modules may be rewritten freely; **entry parameters and output contracts should stay stable**.

## Patching

- **Default: do not patch.** Prefer real service code paths with fixture inputs.
- **Only patch SDKs (or network / process boundaries) that have external side effects** — e.g. `ccxt`, `yfinance`, `akshare`, HTTP clients. SDK surfaces are relatively stable compared to our internals.
- **Do not monkeypatch our own modules** (`src.services.*`, private methods). If a test needs that, the design or the test is wrong — go through `Service.run` instead (or inject a real dependency service that itself only patches SDKs).
- Pure computation (validators, formatters, pure transforms) needs **no patch**; call via the service entrypoint or a public function and assert outputs.

## What to patch vs not

| Layer | Patch? | Instead |
|-------|--------|---------|
| Service public `run` I/O | No | `await Service(cfg).run({...})` with fixture inputs |
| Atomic Operation (unit) | No | Call Operation directly; assert return value |
| Internal helpers | No | Reach them via Service entry + config |
| External SDK (`ccxt`, etc.) | Yes, when the test would otherwise hit the network | Fake SDK module / exchange class |
| Pure logic | No | Assert outputs |

## Markers

- `@pytest.mark.unit` — fast, no real network; SDK may be faked.
- `@pytest.mark.integration` — broader wiring when present; still avoid live exchange calls unless explicitly intended.

## Example shape (service + side-effect SDK)

```python
from unittest.mock import AsyncMock, patch

import pytest

from src.services.binance_perp import BinancePerp, BinancePerpConfig


@pytest.mark.unit
@pytest.mark.asyncio
async def test_binance_perp_balance():
    class FakeExchange:
        def __init__(self, *a, **k):
            self.fetch_balance = AsyncMock(
                return_value={"free": {"USDT": 1000.0}, "used": {"USDT": 0.0}, "total": {"USDT": 1000.0}, "info": {}}
            )
            self.close = AsyncMock()
            self.set_sandbox_mode = AsyncMock()

    fake_ccxt = type("ccxt", (), {"binanceusdm": FakeExchange})()
    svc = BinancePerp(BinancePerpConfig(exchange="binance", product="usdm", sandbox=True))

    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt}):
        result = await svc.run({"action": "balance"})

    assert result.success is True
    assert result.data["result"]["assets"]["USDT"]["total"] == 1000.0
```

Notes:

- Construct the service with a real `*Config` model (no patching of our config types).
- Only `ccxt.async_support` is replaced — that is the side-effect SDK.
- Validation, dry_run policy, response trimming, etc. all run for real through `Service.run`.
