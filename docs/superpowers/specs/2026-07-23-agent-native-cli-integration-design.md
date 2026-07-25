# OpenQuantMaster — Agent Native CLI Integration Design

## Document Control

- **Date**: 2026-07-23
- **Status**: Approved
- **Author**: Claude Code (collaborative session with project owner)
- **Related documents**:
  - `2026-07-19-agent-integration-demo-design.md` (superseded demo design — the flag-based `--skill/--artifact` CLI contract is replaced by this design)
  - `2026-07-19-agent-integration-design.md` (full Agent integration design)
- **Decision**: Replace the flag-based `CliBackend` contract with **native CLI invocation**: OpenQuantMaster becomes an Agent workspace (`.claude/`, `.agents/`, `CLAUDE.md`/`AGENTS.md`), and pipeline Agent stages invoke real Agent CLIs (`claude`, `codex`, `kimi`, …) with a minimal prompt. Skills and tools are exposed as workspace-native skills; memory is a structured lesson store accessed via runtime CLI tools.

---

## 1. Purpose and Scope

### 1.1 Goal

An Agent stage in a pipeline should:

1. Run a **real** Agent CLI (Claude Code, Codex, Kimi, …) inside the OpenQuantMaster project directory.
2. Receive a minimal prompt: which skill to use, where the input artifact is, where to write output.
3. Read the skill itself, read artifacts with its own native file tools (Read/Bash), and autonomously decide whether to call OpenQuantMaster tools (`python -m runtime.cli tool ...`).
4. Read and write its own structured lessons (memory) so it can improve across runs.
5. Write the final report to the pipeline-specified output directory, with a one-line summary marker.

### 1.2 Scope

- **Adapter layer** in `runtime/agent_gateway/adapters/` — one adapter per CLI (`claude`, `codex`, `kimi`, `generic`).
- **`init-workspace` CLI command** — generates workspace files per target CLI (Claude Code, Codex, or all).
- **Workspace skill set** — `oqm-tool`, plus business skills synced from `skills/core/`.
- **`CliBackend` refactor** — delegates argv composition to adapters; keeps subprocess/timeout/output handling.
- **Pipeline contract unchanged** — `agent_tool` input/output schema stays as in the demo design.

**Deferred (explicitly out of this implementation round):** memory tools (`read_memory_tool` / `write_memory_tool`), the `read-memory` / `write-memory` skills, and the structured lesson store (§6). The design for them is kept below as the agreed target; implementation happens in a later round.

### 1.3 Non-goals

- No MCP server implementation.
- No PTY / interactive session management (headless one-shot only for now).
- No JSONL stream parsing of CLI output (report file is the contract; stdout is a fallback).
- No permission sandboxing of the Agent CLI beyond what each CLI natively supports.

---

## 2. Architecture

```text
Pipeline Runner (stage: agent_analyze)
        │ AgentTask { skill_path, task_description, previous_artifact_path, output_dir, ... }
        ▼
   AgentDriver  ── selects adapter by config.agent.adapter
        │
        ▼
  BaseAdapter (claude | codex | kimi | generic)
        │  compose_command(task, env) → argv + env + cwd
        ▼
   CliBackend
        │  subprocess (cwd = project root), timeout, kill, stdout capture
        │  report.md recovery + summary extraction
        ▼
   AgentResult { success, report_artifact, summary, error }
```

The Agent CLI subprocess runs with **cwd = OpenQuantMaster project root**, so it discovers `.claude/` / `.agents/` / `CLAUDE.md` / `AGENTS.md` natively, can Read files, and can run `python -m runtime.cli tool ...`.

### Components

| Component | Responsibility |
|-----------|----------------|
| `BaseAdapter` | Interface: `compose_command(task) -> AdapterCommand { argv, env, cwd }` |
| `ClaudeAdapter` | `claude -p "<prompt>" --allowed-tools "Read,Write,Edit,Bash,Skill"` |
| `CodexAdapter` | `codex exec "<prompt>"` with sandbox/approval config flags |
| `KimiAdapter` | `kimi -p "<prompt>"` (argv shape confirmed at implementation time) |
| `GenericAdapter` | User-configured `default_cli` + `prompt_flag` + `headless_args` |
| `CliBackend` | Prepare output dir, spawn subprocess, timeout/kill, recover `report.md`, extract summary |
| `AgentDriver` | Instantiate adapter from config, hand to `CliBackend` |
| `init-workspace` | Generate workspace files per target CLI |
| `read_memory_tool` / `write_memory_tool` | Structured lesson store |
| `agent_tool` (pipeline stage) | Unchanged interface; delegates to `AgentDriver` |

---

## 3. Workspace Initialization

Command:

```bash
python -m runtime.cli init-workspace --agent claude   # .claude/ + CLAUDE.md
python -m runtime.cli init-workspace --agent codex    # .agents/ + AGENTS.md
python -m runtime.cli init-workspace --agent kimi     # .agents/ + AGENTS.md (until kimi has a native dir)
```

`--agent` is required and repeatable (e.g. `--agent claude --agent codex`); there is no `all` shortcut — targets are always chosen explicitly.

### Generated layout

```text
OpenQuantMaster/
├── CLAUDE.md                       # Claude Code 常驻指令
├── AGENTS.md                       # Codex/opencode 常驻指令（canonical；CLAUDE.md 可 import 它）
├── .claude/
│   ├── settings.json               # 权限：允许 Bash(python -m runtime.cli tool *) 等
│   └── skills/
│       ├── oqm-tool/SKILL.md
│       └── <business skills synced from skills/core/>
└── .agents/
    └── skills/                     # 同一份 skill，供 Codex/opencode 系 CLI 发现
        └── oqm-tool/SKILL.md
```

(`read-memory` / `write-memory` skills are deferred — see §1.2.)

### `CLAUDE.md` / `AGENTS.md` content (minimal, session-agnostic)

These files load in **every** session in the project — including a human's interactive `claude` chat — so they must contain only what is true for all sessions:

- Identity: "This project is OpenQuantMaster, a quant trading pipeline runtime."
- Tool entry point: `python -m runtime.cli tool <tool_name> --inputs '<json>'`.

Nothing else. Stage-specific rules do not belong here.

### Where stage-specific rules live

| Rule | Location | Why |
|------|----------|-----|
| Output contract (`$OQM_OUTPUT_DIR/report.md` + `<!-- summary: -->`) | Injected by the adapter at call time (system-prompt flag when the CLI supports it, e.g. `claude --append-system-prompt`; always also restated in the prompt) | Only applies to headless stage invocations |
| Behavioral constraints (e.g. "never execute trades") | Inside the relevant skill (`skills/core/*.md`) | Constraints are per-workflow, not global; a future trading pipeline may legitimately allow trades |

Business instructions live in skills, not here.

### Init semantics

- Idempotent: existing files are not overwritten unless `--force`.
- `settings.json` merges permissions into an existing file rather than replacing it.
- Business skills are synced from `skills/core/*.md` into both `.claude/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md` (converted to `SKILL.md` frontmatter format: `name`, `description`).

---

## 4. Pipeline Invocation

`agent_tool` builds an `AgentTask`; the selected adapter composes the command. For Claude:

```bash
cd <project root>
OQM_RUN_ID=<run_id> \
OQM_OUTPUT_DIR=artifacts/<run_id>/agent_analyze \
claude -p "加载 skill 'agent_demo'，分析 artifacts/<run_id>/generate_data/demo_data.json，并把最终报告写入 $OQM_OUTPUT_DIR/report.md。" \
  --allowed-tools "Read,Write,Edit,Bash,Skill" \
  --append-system-prompt "You are running as a stage in an OpenQuantMaster pipeline. Write your final report to \$OQM_OUTPUT_DIR/report.md and end it with a line: <!-- summary: <one-sentence summary> -->."
```

Prompt rules:

- Contains **only**: skill name, input artifact path, output dir (via `$OQM_OUTPUT_DIR`), and the stage's `task_description`.
- Never embeds skill content or artifact content — the Agent reads them with its own tools.
- The output contract is additionally injected via the CLI's system-prompt mechanism when available (`--append-system-prompt` for Claude Code; adapters for CLIs without such a flag rely on the prompt text alone).

Adapter-specific argv:

| CLI | Headless invocation |
|-----|---------------------|
| Claude Code | `claude -p <prompt> --allowed-tools "Read,Write,Edit,Bash,Skill"` |
| Codex | `codex -c approval_policy=never -c sandbox_mode=workspace-write exec <prompt>` |
| Kimi | `kimi -p <prompt>` (confirm flag at implementation time) |
| Generic | `<default_cli> <headless_args...> <prompt_flag> <prompt>` |

Environment injected into the subprocess: `OQM_RUN_ID`, `OQM_OUTPUT_DIR`, plus the current process environment.

---

## 5. Output Recovery

- The report contract is `$OQM_OUTPUT_DIR/report.md`.
- Summary extraction (unchanged from demo):
  1. `<!-- summary: ... -->` marker, else
  2. first non-empty line.
- Fallback: if `report.md` is missing but stdout is non-empty, treat stdout as the report content (still success) and write it to `report.md` so downstream stages can read it. Verified for Claude Code (2026-07-23): `claude -p "<prompt>"` in one-shot mode prints only the final response text to stdout (default `--output-format text`). Adapters must therefore use the CLI's plain-text output mode, not a JSON/JSONL mode.
- Missing report **and** empty stdout → `success=False`.

| Scenario | Behavior |
|----------|----------|
| CLI not installed | subprocess spawn fails → stage fails |
| Timeout | kill process → `success=False` |
| returncode ≠ 0 | stderr (or stdout) as error |
| No report.md, non-empty stdout | stdout fallback, success |

---

## 6. Memory (Structured Lessons) — DEFERRED

> **Not implemented in this round** (owner decision, 2026-07-23). This section records the agreed target design for a later iteration. The `read-memory` / `write-memory` skills and memory tools must not be referenced by `CLAUDE.md`/`AGENTS.md` templates or skills until this lands.

Lesson schema:

```json
{
  "timestamp": "2026-07-23T10:00:00Z",
  "context": "BTC market outlook",
  "action": "Suggested long based on momentum",
  "result": "Price dropped 3% within 1h",
  "lesson": "Momentum alone is unreliable without volume confirmation"
}
```

Tools (invoked by the Agent through `python -m runtime.cli tool ...`, wrapped by the `/read-memory` and `/write-memory` skills):

- `read_memory_tool` — inputs: `{ context?, limit = 5 }`; returns the most recent matching lessons as JSON.
- `write_memory_tool` — inputs: `{ context, action, result, lesson }`; appends a lesson.

Storage: append-only JSONL at `data/memory/lessons.jsonl` (path configurable under `paths.data`). Simple, auditable, human-editable. Rotation/querying beyond `limit` is a non-goal for now.

---

## 7. Configuration

`config.yaml` (replaces the demo's `agent` section):

```yaml
agent:
  adapter: claude            # claude | codex | kimi | generic
  default_cli: claude        # executable name/path
  timeout_sec: 300           # default stage timeout; agent_tool input overrides per stage
  workdir: ""                # agent subprocess cwd; bootstrap defaults it to the config file's directory
  headless_args: []          # extra argv passed before the prompt
  generic:
    prompt_flag: "-p"        # generic adapter only
```

The `custom_command` field from the demo design is removed; a custom CLI is expressed via `adapter: generic`.

---

## 8. File Additions and Changes

### New files

```text
runtime/agent_gateway/adapters/
├── __init__.py
├── base.py                  # BaseAdapter, AdapterCommand
├── claude_adapter.py
├── codex_adapter.py
├── kimi_adapter.py
└── generic_adapter.py
runtime/workspace/
├── __init__.py
└── init_workspace.py        # workspace file generation
templates/workspace/
├── CLAUDE.md.tmpl
├── AGENTS.md.tmpl
├── settings.json.tmpl
└── skills/
    └── oqm-tool.SKILL.md
tests/
├── runtime/test_adapters.py
└── runtime/test_init_workspace.py
```

> Deferred to the memory round: `tools/memory/`, `templates/workspace/skills/read-memory.SKILL.md`, `templates/workspace/skills/write-memory.SKILL.md`, `tests/tools/test_memory_tools.py`.

### Modified files

- `runtime/agent_gateway/backends/cli_backend.py` — delegate argv composition to adapter; keep subprocess/timeout/output logic.
- `runtime/agent_gateway/agent_driver.py` — select adapter by `config.agent.adapter`.
- `runtime/config_loader.py` — new `AgentConfig` shape (adapter, generic.prompt_flag; drop `custom_command`, `tool_callback`).
- `runtime/cli.py` — add `init-workspace` subcommand.
- `tests/integration/test_agent_demo_pipeline.py` — updated: fake CLI receives a prompt (not flags); asserts report recovery still works.
- `pyproject.toml` — no new dependencies expected.

### Deleted / superseded

- `scripts/agent_demo_cli.py` — replaced by the fake CLI inside tests.
- Flag contract `--skill/--artifact/--output-dir/--task` — removed.

---

## 9. Testing Strategy

| Type | Test |
|------|------|
| Unit | Each adapter composes correct argv/env/cwd from an `AgentTask` |
| Unit | `init-workspace` generates the full layout per target; idempotent; `--force` overwrites; settings.json merge |
| Unit | `CliBackend` summary extraction and stdout fallback (fake CLI script) |
| Integration | `agent_demo` pipeline end-to-end with a fake CLI executable (writes `report.md`), asserting stage success, report artifact, real artifact content used, and notify body |

No live network calls; PushPlus remains mocked as in the demo.

---

## 10. Migration from the Demo Implementation

1. Land adapters + `CliBackend` refactor behind the new config (`agent.adapter`).
2. Land `init-workspace` + templates.
3. Update `agent_demo` integration test to the prompt contract.
4. Update `AGENT_GUIDE.md`: document `init-workspace`, workspace layout, and how to add a new CLI adapter.
5. Remove `scripts/agent_demo_cli.py` and the old flag contract.

Memory tools and skills (§6) land in a follow-up round after this migration is verified.

The demo design (`2026-07-19-agent-integration-demo-design.md`) is superseded in the parts concerning the Agent CLI contract; its pipeline/notifier portions remain valid.
