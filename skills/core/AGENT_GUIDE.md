# AGENT_GUIDE — OpenQuantMaster

## Project overview

`OpenQuantMaster` is an agent-first quantitative trading pipeline runtime (Python).

Core components:

- `runtime/` — daemon, bootstrap, config, scheduler, event bus, state store, pipeline runner.
- `tools/` — auto-discovered tools. Key tools:
  - `vibe_tool` — unified gateway to Vibe-Trading (backtest, research, alpha bench, swarm, etc.)
  - `ohlcv_tool` — fetch market data
  - `signal_scan_tool` — scan Vibe-Trading run directories for signals
  - `notify_tool` — send notifications
  - `agent_tool` — run an external agent on an artifact
- `pipelines/` — YAML workflow manifests.
- `schemas/` — JSON schemas for manifests and tool results.

## Conventions

- Python 3.12+, asyncio everywhere.
- Single `pyproject.toml` for deps and tool config.
- All tools subclass `tools.base.BaseTool`.
- All persistence goes through `runtime.state_store.StateStore`.
- `bootstrap.py` is the only composition root.
- Use `python -m runtime.cli list-tools` to inspect the live tool registry.

## Running

```bash
pip install -e ".[dev]"
quantmaster-daemon --preflight
quantmaster-daemon --run hello_pipeline
```

## Vibe-Trading

Install the optional dependency:

```bash
pip install -e ".[vibe]"
```

Configure the LLM provider in `~/.vibe-trading/.env`, then use `vibe_tool` in pipelines or via the CLI.
