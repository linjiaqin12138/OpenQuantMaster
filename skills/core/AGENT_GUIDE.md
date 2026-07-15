# AGENT_GUIDE — OpenQuantMaster

## Project overview

`OpenQuantMaster` is an agent-first quantitative trading daemon.
Milestone 1 implements a minimal runtime skeleton:
- `runtime/` — daemon, bootstrap, config, scheduler, event bus, state store, pipeline runner.
- `tools/` — auto-discovered tools; only `echo_tool` is implemented.
- `pipelines/` — YAML workflow manifests.
- `schemas/` — JSON schemas for manifests and tool results.

## Conventions

- Python 3.12+, asyncio everywhere.
- Single `pyproject.toml` for deps and tool config.
- All tools subclass `tools.base.BaseTool`.
- All persistence goes through `runtime.state_store.StateStore`.
- `bootstrap.py` is the only composition root.

## Running

```bash
pip install -e ".[dev]"
quantmaster-daemon --preflight
quantmaster-daemon --run hello_pipeline
```
