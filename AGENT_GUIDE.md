# OpenQuantMaster — Agent Guide

Single entry point for coding assistants.

Start with `skills/core/AGENT_GUIDE.md` for architecture and conventions.
For pipeline YAML details see `skills/core/pipeline_authoring.md`.

Run tests: `pytest -m unit -v`
Run integration tests: `pytest -m integration -v`
Run linter: `ruff check runtime tools tests`

## Agent Integration Demo

The `agent_demo` pipeline demonstrates an external Agent CLI invoked as a pipeline stage.

Run it with:

```bash
quantmaster-daemon --run agent_demo
```

Stages:
1. `generate_data` — writes `demo_data.json`.
2. `agent_analyze` — invokes the configured Agent CLI with skill `skills/core/agent_demo.md`.
3. `notify` — sends the summary via PushPlus.

Configure the Agent CLI and notifier in `config.yaml` under `agent:` and `notifier:`. Set the PushPlus token via environment variable `QUANT_AGENT_NOTIFIER__PUSHPLUS__TOKEN`.

For manual tool invocation:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json_string>'
```
