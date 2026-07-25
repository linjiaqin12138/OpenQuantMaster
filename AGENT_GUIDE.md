# OpenQuantMaster — Agent Guide

Single entry point for coding assistants.

Start with `skills/core/AGENT_GUIDE.md` for architecture and conventions.
For pipeline YAML details see `skills/core/pipeline_authoring.md`.

Run tests: `pytest -m unit -v`
Run integration tests: `pytest -m integration -v`
Run linter: `ruff check runtime tools tests`

## Agent Integration

Pipeline Agent stages invoke a real Agent CLI (`claude`, `codex`, `kimi`, or a
`generic` CLI) headlessly with a minimal prompt. The Agent reads skills and
artifacts itself and writes its report to `$OQM_OUTPUT_DIR/report.md`.

Initialize this repo as an Agent workspace before running Agent stages:

```bash
python -m runtime.cli init-workspace --agent claude   # and/or: --agent codex --agent kimi
```

This generates `CLAUDE.md`/`AGENTS.md`, `.claude/` or `.agents/` skill folders
(including the `oqm-tool` skill and synced business skills from `skills/core/`),
and merges tool-call permissions into `.claude/settings.json`.

Configure the CLI in `config.yaml`:

```yaml
agent:
  adapter: "claude"        # claude | codex | kimi | generic
  default_cli: "claude"
  timeout_sec: 300
  headless_args: []
```

Run the demo pipeline:

```bash
quantmaster-daemon --run agent_demo
```

Stages:
1. `generate_data` — writes `demo_data.json`.
2. `agent_analyze` — invokes the configured Agent CLI with skill `skills/core/agent_demo.md`.
3. `notify` — sends the summary via PushPlus.

Set the PushPlus token via environment variable `QUANT_AGENT_NOTIFIER__PUSHPLUS__TOKEN`.

For manual tool invocation:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json_string>'
```
