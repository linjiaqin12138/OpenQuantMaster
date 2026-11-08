# Testing conventions

## Goals

Tests should survive internal refactors. Prefer stable **public surfaces** — **Service** APIs (`BaseService.run` with documented Pydantic config / input / output) and external SDK APIs — over private helpers.

## Prefer entrypoints

- Drive behavior through a **Service**: construct with its config (or dependencies), then `await service.run({...})`.
- **Operation** unit tests may call a single atomic Operation directly when asserting pure logic or one I/O boundary; do not use that shortcut for multi-step workflows (those belong under Service tests).
- Assert on `ServiceResult` or `OperationResult` (`success`, `data`, `error` as the shared `Error | None` with `code` / `message` / `exception`) and documented output fields. Do not assert on private helpers or internal return types unless they are part of a published contract.
- Internal modules may be rewritten freely; **entry parameters and output contracts should stay stable**.

## Patching

- **Default: do not patch.** Prefer real Service and UseCase code paths with fixture inputs.
- **Concrete Operations may be monkeypatched when testing their callers.** Operations are deliberately thin wrappers around HTTP or other external protocols; their parameters and responses are stable, so they are valid test boundaries. No Operation interface or dependency injection is required solely for testing.
- **External SDKs and network / process boundaries may also be patched** — e.g. `ccxt`, `yfinance`, `akshare`, HTTP clients — especially when testing an Operation itself.
- **Do not monkeypatch other internal objects**, such as private methods, internal helpers, validators, or formatters. Reach them through a Service or UseCase entrypoint instead; their structure may change during refactoring.
- Pure computation needs **no patch**; call it through the public entrypoint or a public function and assert outputs.

## What to patch vs not

| Layer | Patch? | Instead |
|-------|--------|---------|
| Service / UseCase public entrypoint | No | Construct with real config and call its public entrypoint |
| Operation under test | No | Call the Operation directly and patch its external SDK if needed |
| Concrete Operation called by a UseCase | Yes | Replace it with a stable fake return value or exception |
| Internal helpers and private methods | No | Reach them through the public entrypoint |
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
