---
name: oqm-tool
description: How to discover and call OpenQuantMaster pipeline tools from the shell. Use when a task needs data fetching, signal scanning, backtesting, notifications, or agent-driven analysis.
---

# Calling OpenQuantMaster tools

All registered tools are invoked through the runtime CLI:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json>'
```

The command prints a JSON `ToolResult` to stdout. **Always check `success` before using `data`.**

## Discovering tools

To get the live list of registered tools and their JSON schemas:

```bash
python -m runtime.cli list-tools --format json
# or
python -m runtime.cli list-tools --format markdown
```

## Registered tools

| Tool | Capability | Purpose |
|---|---|---|
| `vibe_tool` | vibe | Call Vibe-Trading capabilities (backtest, research, alpha_bench, swarm, etc.). |
| `ohlcv_tool` | market_data | Fetch OHLCV bars for crypto, US, HK, or A-share equities. |
| `signal_scan_tool` | research | Scan a `vibe_runs/` directory for the latest Vibe-Trading signals. |
| `notify_tool` | notification | Send notifications via configured channels. |
| `agent_tool` | agent_gateway | Run a Claude/Codex/Kimi-style agent task on an artifact. |
| `demo_data_tool` | demo | Generate a demo JSON artifact. |
| `echo_tool` | demo | Smoke-test echo. |

### `vibe_tool`

Unified gateway to Vibe-Trading. See the `vibe-trading` skill for installation and provider configuration.

```bash
python -m runtime.cli tool vibe_tool --inputs '{
  "capability": "backtest",
  "inputs": {
    "strategy_description": "dual EMA on SOLUSDT.P",
    "market": "crypto",
    "symbols": ["SOLUSDT.P"],
    "start": "2026-01-01",
    "end": "2026-06-30"
  }
}'
```

Inputs: `capability` (str), `inputs` (dict), `mode` (optional `cli` | `mcp` | `http`), `timeout_sec` (optional int).

Common capabilities:

| Capability | Typical inputs |
|---|---|
| `backtest` | `strategy_description`, `market`, `symbols`, `start`, `end` (or `run_dir` for deterministic replay) |
| `research` | `prompt` or `strategy_description` |
| `alpha_bench` | `zoo`, `universe`, `period` |
| `swarm` | `preset_name`, `task_description` |
| `hypothesis` | `description`, `tags` |
| `web_search` | `query` |

In `mcp` mode, `capability` can also be the raw MCP tool name (e.g. `run_backtest`, `web_search`).

### `ohlcv_tool`

Fetch OHLCV data.

```bash
python -m runtime.cli tool ohlcv_tool --inputs '{
  "symbol": "BTC/USDT",
  "market": "crypto",
  "interval": "1h",
  "limit": 100
}'
```

Inputs: `symbol` (str), `market` (`crypto` | `a_share` | `us_equity` | `hk_equity`), `interval` (str), `start`/`end` (optional ISO date), `limit` (int), `source` (optional `ccxt` | `yfinance` | `tushare` | `akshare`).

Output artifact: CSV with columns `timestamp, open, high, low, close, volume`.

### `signal_scan_tool`

Scan a directory of Vibe-Trading runs for the latest signals matching a `strategy_id`.

```bash
python -m runtime.cli tool signal_scan_tool --inputs '{
  "watch_dir": "./vibe_runs",
  "strategy_id": "dual_ema_v1",
  "market": "crypto"
}'
```

Output artifact: `signals.json` with normalized signal list.

### `notify_tool`

Send a notification through configured channels (e.g. `pushplus`, `telegram`, `email`).

```bash
python -m runtime.cli tool notify_tool --inputs '{
  "subject": "Report",
  "body": "Backtest finished.",
  "channels": ["pushplus"]
}'
```

### `agent_tool`

Run an external agent (Claude/Codex/Kimi) on a previous artifact.

```bash
python -m runtime.cli tool agent_tool --inputs '{
  "skill": "agent_demo",
  "task_description": "Summarize the demo data",
  "pipeline_run_id": "<run-id>"
}'
```

## Common patterns

- **Research loop**: `ohlcv_tool` → `vibe_tool` (backtest) → `signal_scan_tool` → `notify_tool`.
- **Agent analysis**: `demo_data_tool` → `agent_tool`.
- **Cron pipeline**: create a YAML in `pipelines/` with a `trigger` block.

## Troubleshooting

- If `vibe_tool` fails with a Vibe-Trading error, run `vibe-trading provider doctor` and check `~/.vibe-trading/.env`.
- If a tool returns `success: false`, read the `error` field.
- For unsupported markets, use the `source` override or add a loader.
