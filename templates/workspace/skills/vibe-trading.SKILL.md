---
name: vibe-trading
description: How to install, configure, and call the Vibe-Trading backtest/research engine from OpenQuantMaster through the unified vibe_tool.
---

# Vibe-Trading integration

OpenQuantMaster integrates with [Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) through a single OQM tool: `vibe_tool`. The tool dispatches to Vibe-Trading's CLI or MCP server based on `config.yaml`.

## Install

```bash
# as part of the project
pip install -e ".[vibe]"

# or standalone
pip install vibe-trading-ai
```

## Configure the LLM provider

Vibe-Trading reads credentials from `~/.vibe-trading/.env`. Create the file and uncomment exactly one provider block:

```bash
mkdir -p ~/.vibe-trading

# Example: DeepSeek
cat > ~/.vibe-trading/.env <<EOF
LANGCHAIN_PROVIDER=deepseek
LANGCHAIN_MODEL_NAME=deepseek-v4-pro
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
EOF

chmod 600 ~/.vibe-trading/.env
```

Other supported providers use the same pattern (`openrouter`, `openai`, `deepseek`, `ollama`).

Verify the configuration:

```bash
vibe-trading provider doctor
```

## Transport mode

`config.yaml` controls how OQM talks to Vibe-Trading:

```yaml
vibe_trading:
  mode: cli          # cli | mcp | http
  cli_path: vibe-trading
  mcp_command: vibe-trading-mcp
  mcp_url: stdio
  http_url: http://localhost:8899
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

| mode | behavior |
|---|---|
| `cli` | `vibe_tool` calls `vibe-trading` CLI subcommands. No MCP server is started. |
| `mcp` | `vibe_tool` starts `vibe-trading-mcp` and calls tools through stdio JSON-RPC. |
| `http` | Reserved for `vibe-trading serve` HTTP API (not implemented yet). |

## Calling capabilities

### Backtest

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

Deterministic replay (no LLM):

```bash
python -m runtime.cli tool vibe_tool --inputs '{
  "capability": "backtest",
  "inputs": {
    "run_dir": "./vibe_runs/dual_ema_v1_20260716_080000"
  }
}'
```

### Research / natural language

```bash
python -m runtime.cli tool vibe_tool --inputs '{
  "capability": "research",
  "inputs": {
    "prompt": "Analyze recent news about AI hardware and energy geopolitics, then propose a sector rotation strategy"
  }
}'
```

### Alpha benchmark

```bash
python -m runtime.cli tool vibe_tool --inputs '{
  "capability": "alpha_bench",
  "inputs": {
    "zoo": "gtja191",
    "universe": "csi300",
    "period": "2018-2025"
  }
}'
```

## Pipeline example

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

Artifacts produced depend on the capability. `backtest` returns `equity.csv`, `trades.csv`, `metrics.csv`, `run_card.json`.

## Security notes

- `read_only: true` blocks capabilities such as `place_order`, `shell`, and `write_file`.
- Only capabilities listed in `allowed_capabilities` can be invoked.
- Use `python -m runtime.cli list-tools` to see the live registered tool set.
