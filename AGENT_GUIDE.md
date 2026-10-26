# OpenQuantMaster — Agent Guide

Single entry point for coding assistants.

Start with `skills/core/AGENT_GUIDE.md` for architecture and conventions.
For pipeline YAML details see `skills/core/pipeline_authoring.md`.
Engineering norms (especially testing): `docs/conventions/`.

Run tests: `pytest -m unit -v`
Run integration tests: `pytest -m integration -v`
Run linter: `ruff check runtime tools tests`

## Quick commands

```bash
quantmaster-daemon --preflight
quantmaster-daemon --run hello_pipeline
python -m runtime.cli tool <tool_name> --inputs '<json_string>'
python -m runtime.cli list-tools
```
