# OpenQuantMaster

Pipeline + tool quantitative trading daemon. Workflows are YAML pipelines that call registered tools — no external agent inheritance.

## Development setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
quantmaster-daemon --run hello_pipeline
```

## Configuration

Configuration is loaded from `config.yaml` by default. You can override it with the `--config` CLI option or through environment variables prefixed with `QUANT_AGENT_` (nested keys use double underscores, e.g. `QUANT_AGENT_MARKET_DATA__CRYPTO__EXCHANGE=binance`).

### Default `config.yaml`

```yaml
app_name: OpenQuantMaster
environment: development

paths:
  artifacts: ./artifacts
  logs: ./logs
  database: ./data/runtime.db

scheduler:
  timezone: UTC

event_bus:
  backend: memory

logging:
  level: INFO
  format: json

exchanges:
  binance:
    apiKey: ""
    secret: ""
    spot:
      ccxt_id: binance
      sandbox: false
    usdm:
      ccxt_id: binanceusdm
      sandbox: true

market_data:
  crypto:
    exchange: binance
    product: spot
  equities:
    tushare_token: ""
    yfinance_timeout: 30

execution:
  binance_perp:
    exchange: binance
    product: usdm

notifier:
  pushplus:
    enabled: true
    token: ""
```

### Configuration sections

- `paths` — where runtime artifacts, logs, and the SQLite database are stored.
- `scheduler` — default timezone for cron-triggered pipelines.
- `exchanges.binance` — Binance credentials and per-product connection settings (`spot` / `usdm`). Product blocks may override `apiKey`/`secret`.
- `market_data.crypto` — references `exchanges.<name>` via `exchange` + `product` (no embedded keys).
- `execution.binance_perp` — references the USDM product for perpetual trading.
- `market_data.equities` — `tushare_token` for A-share data and `yfinance_timeout` for US/HK equities.
- `notifier` — PushPlus / Telegram / email notification channels.

### Environment variables

See `.env.example`:

```bash
QUANT_AGENT_ENV=development
QUANT_AGENT_DATABASE_URL=sqlite+aiosqlite:///data/runtime.db
QUANT_AGENT_LOG_LEVEL=INFO
```

## CLI usage

Two entry points are installed by `pyproject.toml`:

```bash
# Long-running daemon that schedules cron pipelines and waits for signals
quantmaster-daemon

# Run a single pipeline immediately and exit
quantmaster-run hello_pipeline
```

### Daemon options

```bash
quantmaster-daemon --preflight                  # Check startup health and exit
quantmaster-daemon --run hello_pipeline         # Run one pipeline and exit
quantmaster-daemon --run market_open_review --config ./config.yaml
```

### Tool CLI

```bash
python -m runtime.cli list-tools
python -m runtime.cli tool echo_tool --inputs '{"message":"hi","repeat":1}'
```

## Pipeline manifests

Pipelines live in `pipelines/*.yaml`. A minimal example:

```yaml
name: hello_pipeline
version: "1.0"
description: Smoke-test pipeline using the echo_tool.
stages:
  - name: greet
    tool: echo_tool
    inputs:
      message: "Hello from OpenQuantMaster"
      repeat: 1
    on_failure: stop
```

### Cron triggers

Add a `trigger` block to schedule a pipeline:

```yaml
name: market_open_review
version: "1.0"
description: A-share morning data pull.
trigger:
  type: cron
  cron: "0 9 * * 1-5"
  timezone: "Asia/Shanghai"
stages:
  - name: fetch_watchlist_ohlcv
    tool: ohlcv_tool
    inputs:
      symbol: "000001.SZ"
      market: "a_share"
      interval: "1d"
```

Cron expressions use the standard 5-field format: `minute hour day month day_of_week`. On startup the daemon automatically loads all `pipelines/*.yaml` files and registers cron jobs with APScheduler.

## Tools

Tools are auto-discovered from the `tools/` package via `pkgutil.walk_packages`.

### `ohlcv_tool`

Fetch OHLCV data for crypto, US equities, HK equities, or A-shares.

**Inputs**

| Field    | Required | Description                                                   |
|----------|----------|---------------------------------------------------------------|
| symbol   | yes      | Ticker, e.g. `BTCUSDT`, `AAPL`, `000001.SZ`                   |
| market   | yes      | `crypto`, `us_equity`, `hk_equity`, or `a_share`              |
| interval | yes      | Interval string, e.g. `1d`, `15m`, `1h`                       |
| start    | no       | ISO-8601 start time, e.g. `2025-04-01T00:00:00Z`              |
| end      | no       | ISO-8601 end time                                             |
| limit    | no       | Max rows (default `1000`, max `5000`)                         |
| source   | no       | Force provider: `ccxt`, `yfinance`, `tushare`, or `akshare`   |

**Provider selection**

- `crypto` or `source: ccxt` → CCXT (resolved from `market_data.crypto` → `exchanges.<exchange>.<product>`).
- `us_equity` / `hk_equity` or `source: yfinance` → yfinance.
- `a_share` → tushare if `tushare_token` is set, otherwise akshare.

**Example pipeline**

```yaml
name: crypto_15m_data
version: "1.0"
stages:
  - name: fetch_sol
    tool: ohlcv_tool
    inputs:
      symbol: "SOLUSDT.P"
      market: "crypto"
      interval: "15m"
      limit: 500
```

Run it:

```bash
quantmaster-run crypto_15m_data
```

Output is a CSV artifact stored under `./artifacts/<run_id>/fetch_sol/ohlcv_SOLUSDT.P_15m.csv`.

### `binance_perp_tool`

Binance USDT-M perpetual trading via CCXT (`binanceusdm`). Credentials come from `exchanges.binance` (referenced by `execution.binance_perp`). Write actions default to `dry_run: true`.

**Actions**

| action | Notes |
|--------|--------|
| `balance` / `positions` / `open_orders` | Read; `symbol` optional for positions/orders |
| `create_order` | `market`, `limit`, `stop_market`, `take_profit_market`, `stop`, `take_profit`, `trailing_stop_market` |
| `cancel_order` | Requires `order_id` + `symbol` |
| `set_leverage` / `set_margin_mode` | Per symbol |
| `set_position_mode` | `hedge: true/false` |

**CLI examples**

```bash
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"balance"}'
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"create_order","symbol":"BTC/USDT:USDT","side":"buy","order_type":"market","amount":0.001}'
python -m runtime.cli tool binance_perp_tool --inputs '{"action":"create_order","symbol":"BTC/USDT:USDT","side":"sell","order_type":"stop_market","amount":0.001,"stop_price":45000,"reduce_only":true,"dry_run":false}'
```

### Other built-in tools

- `indicator_tool` — compute technical indicators from OHLCV artifacts (see `docs/tools/indicator_tool.md`).
- `notify_tool` — send notifications via configured channels.
- `parallel_tool` — run multiple registered tools concurrently.
- `echo_tool` / `demo_data_tool` — smoke and demo helpers.

## Inspecting results

### Artifacts

Each pipeline run writes artifacts under:

```
./artifacts/<pipeline_run_id>/<stage_name>/<artifact_name>
```

### Pipeline runs in the database

Pipeline runs, stage runs, artifact references, and signals are persisted in `./data/runtime.db` (SQLite). You can query them directly:

```bash
sqlite3 ./data/runtime.db "SELECT id, name, status, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 10;"
```

## Testing and linting

```bash
# Unit tests only (fast, no network)
pytest -m unit -v

# Integration tests (uses temporary SQLite, may call external APIs)
pytest -m integration -v

# All tests
pytest -v

# Linter
ruff check runtime tools tests
```

Test markers are configured in `pyproject.toml`:

- `unit` — fast tests with mocks.
- `integration` — tests that spin up the real runtime stack.

## Project layout

```
.
├── config.yaml.example      # Sample runtime configuration
├── pipelines/               # Pipeline manifests
├── runtime/                 # Daemon, scheduler, state store, runner
├── schemas/                 # JSON schemas for contracts
├── skills/                  # Coding-assistant guides
├── tools/                   # Tool implementations
│   ├── demo/                # echo_tool, demo_data_tool
│   ├── market_data/         # ohlcv_tool, indicator_tool
│   ├── notifier/            # notify_tool
│   └── runtime/             # parallel_tool
└── tests/                   # pytest suite
```

## License

MIT
