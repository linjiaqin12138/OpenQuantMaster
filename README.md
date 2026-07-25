# OpenQuantMaster

Agent-first quantitative trading daemon.

## Development setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
quantmaster-daemon --run hello_pipeline
```

## Configuration

Configuration is loaded from `config.yaml` by default. You can override it with the `--config` CLI option or through environment variables prefixed with `QUANT_AGENT_` (nested keys use double underscores, e.g. `QUANT_AGENT_MARKET_DATA__CRYPTO__DEFAULT_EXCHANGE=binance`).

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

market_data:
  crypto:
    default_exchange: binance
    sandbox: false
    exchange_keys: {}
  equities:
    tushare_token: ""
    yfinance_timeout: 30

vibe_trading:
  mode: cli
  cli_path: vibe-trading
  mcp_command: vibe-trading-mcp
  mcp_url: stdio
  http_url: http://localhost:8000
  auto_start_mcp: true
  read_only: true
  allowed_capabilities:
    - backtest
    - research
    - alpha_bench
    - swarm
    - hypothesis
    - web_search
```

### Configuration sections

- `paths` — where runtime artifacts, logs, and the SQLite database are stored.
- `scheduler` — default timezone for cron-triggered pipelines.
- `market_data.crypto` — default crypto exchange and optional API keys.
- `market_data.equities` — `tushare_token` for A-share data and `yfinance_timeout` for US/HK equities.
- `vibe_trading` — transport and security settings for the unified `vibe_tool` (`cli`, `mcp`, or `http`).

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
quantmaster-daemon --run backtest_demo --config ./config.yaml
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

## Milestone 2 tools

Tools are auto-discovered from the `tools/` package via `pkgutil.walk_packages`. Milestone 2 adds market data and research tools.

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

- `crypto` or `source: ccxt` → CCXT (exchange from `market_data.crypto.default_exchange`).
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

### `vibe_tool`

Unified gateway to [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading). It exposes Vibe-Trading capabilities (backtest, research, alpha bench, swarm, etc.) as a single OQM tool. Transport is controlled by `vibe_trading.mode` in `config.yaml`.

**Dependency**

```bash
pip install -e ".[vibe]"
# or standalone
pip install vibe-trading-ai
```

**Configuring the LLM provider**

Vibe-Trading reads provider credentials from `~/.vibe-trading/.env`. Create that
file and uncomment exactly one provider block:

```bash
mkdir -p ~/.vibe-trading

cat > ~/.vibe-trading/.env <<EOF
LANGCHAIN_PROVIDER=deepseek
LANGCHAIN_MODEL_NAME=deepseek-v4-pro
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
EOF

chmod 600 ~/.vibe-trading/.env
```

Other supported providers use the same pattern (`openrouter`, `openai`, `ollama`).

Verify the configuration:

```bash
vibe-trading provider doctor
```

**Inputs**

| Field     | Required | Description                                                        |
|-----------|----------|--------------------------------------------------------------------|
| capability | yes      | Vibe-Trading capability: `backtest`, `research`, `alpha_bench`, `swarm`, `hypothesis`, `web_search`, or raw MCP tool name. |
| inputs    | no       | Capability-specific arguments.                                     |
| mode      | no       | Override `vibe_trading.mode` (`cli`, `http`, or `mcp`).            |
| timeout_sec | no     | Per-call timeout.                                                  |

**Example pipeline**

```yaml
name: backtest_demo
version: "1.0"
description: Research-only backtest runner.
trigger:
  type: manual
stages:
  - name: backtest
    tool: vibe_tool
    inputs:
      capability: "backtest"
      inputs:
        strategy_description: "dual EMA on SOLUSDT.P"
        market: "crypto"
        symbols: ["SOLUSDT.P"]
        start: "2026-01-01"
        end: "2026-06-30"
```

For deterministic replay of an existing Vibe-Trading run:

```yaml
stages:
  - name: backtest
    tool: vibe_tool
    inputs:
      capability: "backtest"
      inputs:
        run_dir: "./vibe_runs/dual_ema_v1_20260716_080000"
```

Artifacts produced by `backtest`: `equity.csv`, `trades.csv`, `metrics.csv`, and `run_card.json`.

### `signal_scan_tool`

Scan a `vibe_runs/` directory for the latest Vibe-Trading run that matches a `strategy_id`, normalize its `signals.json`, and emit a JSON artifact.

**Inputs**

| Field       | Required | Description                                  |
|-------------|----------|----------------------------------------------|
| watch_dir   | yes      | Directory to scan for run folders.           |
| strategy_id | yes      | Strategy ID to match in `run_card.json`.     |
| market      | yes      | Default market for signals without one.      |

**Example pipeline**

```yaml
name: crypto_signal_fired
version: "1.0"
description: 15-minute crypto scan using CCXT data and Vibe-Trading signals.
trigger:
  type: cron
  cron: "*/15 * * * *"
  timezone: UTC
stages:
  - name: fetch_ohlcv
    tool: ohlcv_tool
    inputs:
      symbol: "SOLUSDT.P"
      market: "crypto"
      interval: "15m"

  - name: scan_signals
    tool: signal_scan_tool
    inputs:
      strategy_id: "dual_ema_v1"
      market: "crypto"
      watch_dir: "./vibe_runs"
```

## Inspecting results

### Artifacts

Each pipeline run writes artifacts under:

```
./artifacts/<pipeline_run_id>/<stage_name>/<artifact_name>
```

For example:

```bash
ls ./artifacts/$(ls ./artifacts | tail -n 1)/fetch_sol/
```

### Pipeline runs in the database

Pipeline runs, stage runs, artifact references, and signals are persisted in `./data/runtime.db` (SQLite). You can query them directly:

```bash
sqlite3 ./data/runtime.db "SELECT id, name, status, created_at FROM pipeline_runs ORDER BY created_at DESC LIMIT 10;"
```

### Signals

Signals generated by `signal_scan_tool` are stored in the `signals` table. Query the latest signals for a strategy:

```bash
sqlite3 ./data/runtime.db "SELECT strategy_id, symbol, side, strength, status, triggered_at FROM signals ORDER BY triggered_at DESC LIMIT 10;"
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
├── config.yaml              # Default runtime configuration
├── pipelines/               # Pipeline manifests
├── runtime/                 # Daemon, scheduler, state store, runner
├── schemas/                 # JSON schemas for contracts
├── skills/                  # Agent skill definitions
├── tools/                   # Tool implementations
│   ├── demo/                # echo_tool
│   ├── market_data/         # ohlcv_tool
│   └── research/            # backtest_tool, signal_scan_tool
└── tests/                   # pytest suite
```

## License

MIT
