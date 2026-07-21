# OpenQuantMaster — Agent Integration Demo Implementation Plan

## Document Control

- **Date**: 2026-07-20
- **Status**: Approved for execution
- **Author**: Claude Code
- **Source design**: `docs/superpowers/specs/2026-07-19-agent-integration-demo-design.md`

## Goal

Implement the minimal 3-stage `agent_demo` pipeline that proves an external Agent CLI can be invoked as a pipeline stage, read a previous stage artifact, produce a new artifact, and trigger a PushPlus notification in the next stage.

## Task Summary

| Task | Focus | New files | Modified files |
|------|-------|-----------|----------------|
| 15 | Config, bootstrap, and CLI extension | — | `pyproject.toml`, `config.yaml`, `runtime/config_loader.py`, `runtime/bootstrap.py`, `runtime/cli.py` |
| 16 | Agent Gateway + `agent_tool` | `runtime/agent_gateway/*`, `tools/agent/*` | — |
| 17 | Notifier package + `notify_tool` | `runtime/notifier/*`, `tools/notifier/*` | — |
| 18 | Demo data tool, skill, pipeline YAML | `tools/demo/demo_data_tool.py`, `skills/core/agent_demo.md`, `pipelines/agent_demo.yaml` | — |
| 19 | Tests | `tests/runtime/*`, `tests/tools/*`, `tests/integration/*` | — |
| 20 | Docs update and final verification | — | `AGENT_GUIDE.md`, `progress.md` |

## Task 15: Config, Bootstrap, and CLI Extension

**Modified files:**
- `pyproject.toml` — confirm `httpx` is present in dev deps (already present); add `runtime/notifier*` and `tools/agent*` / `tools/notifier*` to package discovery if needed.
- `config.yaml` — add `agent`, `mcp`, and `notifier` sections from the design doc.
- `runtime/config_loader.py` — add `AgentConfig`, `McpConfig`, `PushplusConfig`, `TelegramConfig`, `EmailConfig`, `NotifierConfig`, and attach them to `RuntimeConfig`.
- `runtime/bootstrap.py` — initialize `AgentDriver` and `build_notifier(config.notifier)` after tool registry setup; pass `agent_driver` to `PipelineRunner` (extend runner constructor if needed).
- `runtime/cli.py` — add `tool` subcommand: `python -m runtime.cli tool <tool_name> --inputs '<json_string>'`.

**Interfaces:**
- Consumes: existing `RuntimeConfig`, `BootstrapResult`, `PipelineRunner`.
- Produces: agent/notifier configuration models, CLI tool callback entry point, initialized driver/notifier in bootstrap.

**Steps:**
1. Add config models. `AgentConfig` must expose `default_cli`, `custom_command`, `timeout_sec`, `max_iterations`, `tool_callback`, `headless_args`. Notifier configs expose `enabled` and channel-specific secrets.
2. Update `config.yaml` so it can be loaded without errors.
3. In `bootstrap.py`, instantiate `AgentDriver(config.agent)` and `CompositeNotifier` via `build_notifier(config.notifier)`. Add both to `BootstrapResult`.
4. Extend `PipelineRunner.__init__` to accept optional `agent_driver` and `notifier` arguments; store as attributes.
5. Implement `runtime/cli.py::tool` command: parse JSON inputs, look up tool from a fresh `ToolRegistry` (or bootstrap), execute, print `ToolResult.model_dump_json()`.

**Verification:**
- `python -m runtime.cli tool echo_tool --inputs '{"message":"test","repeat":1}'` prints a successful `ToolResult`.
- `quantmaster-daemon --preflight` passes with updated config.

## Task 16: Agent Gateway and agent_tool

**New files:**
- `runtime/agent_gateway/__init__.py`
- `runtime/agent_gateway/agent_task.py`
- `runtime/agent_gateway/agent_result.py`
- `runtime/agent_gateway/backends/__init__.py`
- `runtime/agent_gateway/backends/base.py`
- `runtime/agent_gateway/backends/cli_backend.py`
- `runtime/agent_gateway/backends/mcp_backend.py` — raises `NotImplementedError`
- `runtime/agent_gateway/backends/http_backend.py` — raises `NotImplementedError`
- `runtime/agent_gateway/agent_driver.py`
- `tools/agent/__init__.py`
- `tools/agent/agent_tool.py`

**Interfaces:**
- `AgentTask` carries `skill_path`, `task_description`, `previous_artifact_path`, `output_dir`, `pipeline_run_id`, `timeout_sec`.
- `AgentResult` carries `success`, `report_artifact`, `summary`, `error`.
- `BaseBackend.run(task: AgentTask) -> AgentResult` is async.
- `CliBackend` builds a shell command: `<cli> --skill <skill_path> --artifact <artifact_path> --output-dir <output_dir> --task <task_description>` (exact args TBD to match the fake Agent CLI used in tests).
- `AgentDriver` selects backend via `config.tool_callback` and delegates to `CliBackend` for the demo.
- `AgentTool` input: `skill`, `task_description`, `timeout_sec`. Output: `success`, `report_artifact`, `summary`.

**Steps:**
1. Define `AgentTask` and `AgentResult` pydantic models.
2. Define abstract `BaseBackend` with `async def run(self, task: AgentTask) -> AgentResult`.
3. Implement `CliBackend`:
   - Resolve `skill` to `skills/<skill>.md`.
   - Discover the previous artifact from the run context: `artifacts/<run_id>/generate_data/demo_data.json`.
   - Ensure output directory `artifacts/<run_id>/agent_analyze/` exists.
   - Build CLI command from `config.default_cli` / `config.custom_command` plus headless args.
   - Run subprocess with timeout; capture stdout/stderr.
   - Read `report.md` from output dir; extract summary (first paragraph or a `<!-- summary: ... -->` marker).
4. Implement `McpBackend` and `HttpBackend` as stubs raising `NotImplementedError`.
5. Implement `AgentDriver`: holds config, instantiates backend, exposes `async def run(task) -> AgentResult`.
6. Implement `AgentTool`: validate inputs, build `AgentTask` from run context, call driver, return `ToolResult` with report artifact and summary.

**Verification:**
- Unit test: `AgentDriver` constructs expected CLI command from mock config.
- Unit test: `CliBackend.run` with a fake script writes `report.md` and returns correct `AgentResult`.

## Task 17: Notifier Package and notify_tool

**New files:**
- `runtime/notifier/__init__.py`
- `runtime/notifier/base.py`
- `runtime/notifier/pushplus_notifier.py`
- `runtime/notifier/telegram_notifier.py` — no-op stub
- `runtime/notifier/email_notifier.py` — no-op stub
- `runtime/notifier/composite.py`
- `tools/notifier/__init__.py`
- `tools/notifier/notify_tool.py`

**Interfaces:**
- `Notifier` abstract class with `async def send(subject: str, body: str) -> dict[str, Any]`.
- `PushplusNotifier.send` uses `httpx.AsyncClient` POST to `http://www.pushplus.plus/send` with `token`, `title`, `content`. Returns `{"pushplus": "ok"}` on 200, else failure dict.
- `TelegramNotifier` and `EmailNotifier` return `{"<channel>": "not_implemented"}`.
- `CompositeNotifier` iterates enabled channels and aggregates results.
- `build_notifier(config: NotifierConfig) -> CompositeNotifier`.
- `NotifyTool` input: `subject`, `body`, `channels: list[str]`. Output: `success`, `results`.

**Steps:**
1. Define abstract `Notifier`.
2. Implement `PushplusNotifier` with token-from-config; missing token returns `success=False` and `"missing token"`.
3. Implement no-op `TelegramNotifier` and `EmailNotifier`.
4. Implement `CompositeNotifier` and `build_notifier`.
5. Implement `NotifyTool`: take subject/body, call composite notifier, return results.

**Verification:**
- Unit test: `notify_tool` only calls PushPlus when configured; stubs return `not_implemented`.
- Unit test: missing PushPlus token returns `success=False`.

## Task 18: Demo Data Tool, Skill, and Pipeline YAML

**New files:**
- `tools/demo/demo_data_tool.py`
- `skills/core/agent_demo.md`
- `pipelines/agent_demo.yaml`

**Interfaces:**
- `DemoDataTool` input: `topic`. Output: `topic`, `rows`, `artifact`. Writes `demo_data.json` to `artifacts/<run_id>/generate_data/demo_data.json`.
- `skills/core/agent_demo.md` follows the design doc template.
- `pipelines/agent_demo.yaml` follows the design doc manifest.

**Steps:**
1. Implement `DemoDataTool` with deterministic JSON output.
2. Write `skills/core/agent_demo.md` with placeholders for `pipeline_run_id`, artifact paths, and output dir.
3. Write `pipelines/agent_demo.yaml` with 3 stages.

**Verification:**
- Unit test: `demo_data_tool` produces correct JSON artifact.
- `quantmaster-daemon --run agent_demo` executes (integration test will mock Agent CLI).

## Task 19: Tests

**New files:**
- `tests/runtime/test_agent_driver.py`
- `tests/runtime/test_notifier.py`
- `tests/tools/test_agent_tool.py`
- `tests/tools/test_notify_tool.py`
- `tests/tools/test_demo_data_tool.py`
- `tests/integration/test_agent_demo_pipeline.py`

**Coverage:**
- `test_demo_data_tool`: deterministic artifact and output model.
- `test_agent_driver`: CLI command construction; fake backend run.
- `test_agent_tool`: run with mocked driver, assert report artifact and summary.
- `test_notifier`: PushPlus success, missing token, API failure; Telegram/Email stubs.
- `test_notify_tool`: channel routing and result aggregation.
- `test_agent_demo_pipeline`: run full pipeline with a fake Agent CLI script; assert `report.md` exists and PushPlus notifier is called with summary.

**Constraints:**
- No live network calls; mock `httpx.AsyncClient` for PushPlus.
- Use temporary directories for artifacts.

## Task 20: Documentation Update and Final Verification

**Modified files:**
- `AGENT_GUIDE.md` — mention `agent_demo` pipeline, `runtime/cli tool` usage, and `skills/core/agent_demo.md`.
- `progress.md` — add task 15–20 status.

**Final verification steps:**
1. `pytest -m unit -v` — all pass.
2. `pytest -m integration -v` — all pass.
3. `ruff check runtime tools tests` — clean.
4. `quantmaster-daemon --config config.yaml --preflight` — passes.
5. `quantmaster-daemon --run agent_demo` — completes with status `completed`.

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-07-19-agent-integration-demo-plan.md`.
Task briefs saved to `.superpowers/sdd/task-{15..20}-brief.md`.

Execution options:

1. **Subagent-Driven (recommended)** — Dispatch a fresh subagent per task, review between tasks, fast iteration. Required sub-skill: `superpowers:subagent-driven-development`.
2. **Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`, batch execution with checkpoints. Required sub-skill: `superpowers:executing-plans`.

Which approach would you like to use?
