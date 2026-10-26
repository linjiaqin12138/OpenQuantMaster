# AGENT_GUIDE — OpenQuantMaster

## Project overview

`OpenQuantMaster` is a pipeline + tool quantitative trading runtime (Python).
No external agent inheritance: workflows are YAML pipelines that call registered tools.

Core components:

- `runtime/` — daemon, bootstrap, config, scheduler, event bus, state store, pipeline runner.
- `tools/` — auto-discovered tools. Key tools:
  - `ohlcv_tool` — fetch market data
  - `indicator_tool` — compute technical indicators
  - `notify_tool` — send notifications
  - `parallel_tool` — run registered tools concurrently
  - `echo_tool` / `demo_data_tool` — smoke / demo helpers
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
