# Testing conventions

## Goals

Tests should survive internal refactors. Prefer stable **public surfaces** (CLI, tool `--inputs` contract, SDK APIs) over private helpers.

## Prefer entrypoints

- Drive behavior through the **CLI entry** (or other documented public API), not by importing and calling internal helpers.
- For tools, the stable entry is:

  ```bash
  python -m runtime.cli tool <tool_name> --inputs '<json>' [--config path]
  ```

  In tests, invoke the Click CLI (e.g. `click.testing.CliRunner`) against `runtime.cli.cli`, not `SomeTool()._private_method(...)`.
- Assert on CLI exit code and stdout/stderr JSON (or documented output shape). Do not assert on private return types unless they are part of a published contract.
- Internal modules may be rewritten freely; **entry parameters and output contracts should stay stable**.

## Patching

- **Default: do not patch.** Prefer real code paths with fixtures / temp dirs / seeded data.
- **Only patch SDKs (or network / process boundaries) that have external side effects** — e.g. `ccxt`, HTTP clients, brokers. SDK surfaces are relatively stable compared to our internals.
- **Do not monkeypatch our own internal functions** (`runtime.*`, `tools.*.*_helper`, private methods). If a test needs that, the design or the test is wrong — go through the entrypoint instead.
- Pure computation (validators, formatters, pure transforms) needs **no patch**; call via the entrypoint or a public function and assert outputs.
- **Do not patch the database / ORM / repository layer.** Seed real rows (or use a temp SQLite file) so transaction boundaries, session lifecycle, and commit/rollback bugs can still surface.

## What to patch vs not

| Layer | Patch? | Instead |
|-------|--------|---------|
| CLI / tool public inputs | No | Invoke CLI |
| Internal helpers / resolvers | No | Reach them via entry + config |
| External SDK (`ccxt`, etc.) | Yes, when the test would otherwise hit the network | Fake SDK module / exchange class |
| Pure logic | No | Assert outputs |
| DB / StateStore | No | Temp DB + seed data |

## Markers

- `@pytest.mark.unit` — fast, no real network; SDK may be faked.
- `@pytest.mark.integration` — broader wiring (bootstrap, pipelines, real temp DB); still avoid live exchange calls unless explicitly intended.

## Example shape (tools + side-effect SDK)

```python
from click.testing import CliRunner
from unittest.mock import AsyncMock, patch

from runtime.cli import cli

def test_binance_perp_balance_via_cli(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("...")  # real config file

    class FakeExchange:
        def __init__(self, *a, **k):
            self.fetch_balance = AsyncMock(return_value={...})
            self.close = AsyncMock()
            self.set_sandbox_mode = AsyncMock()

    fake_ccxt = type("ccxt", (), {"binanceusdm": FakeExchange})()

    with patch.dict("sys.modules", {"ccxt.async_support": fake_ccxt}):
        result = CliRunner().invoke(
            cli,
            ["tool", "binance_perp_tool", "--inputs", '{"action":"balance"}'],
        )

    assert result.exit_code == 0
    # parse stdout JSON ToolResult and assert contract fields
```

Notes:

- Config is a real file under `tmp_path` (no patching `load_config` internals).
- Only `ccxt.async_support` is replaced — that is the side-effect SDK.
- Discovery, validation, dry_run, trimming, etc. all run for real through the CLI path.
