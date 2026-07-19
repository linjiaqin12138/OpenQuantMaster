# OpenQuantMaster — Agent Integration Demo Design

## Document Control

- **Date**: 2026-07-19
- **Status**: Draft for review
- **Author**: Claude Code (collaborative session with project owner)
- **Related documents**:
  - `docs/superpowers/specs/2026-07-19-agent-integration-design.md` (full Agent integration design — preserved)
  - `docs/superpowers/specs/2026-07-12-agent-trading-system-design.md` (system design)
- **Decision**: Build a **minimal end-to-end demo** that proves an external Agent CLI can be invoked as a pipeline stage, read a previous stage's artifact, produce a new artifact, and trigger a PushPlus notification in the next stage.

---

## 1. Purpose and Scope

### 1.1 Goal

Validate the Agent Gateway architecture with the smallest possible working slice:

1. A 3-stage pipeline runs end-to-end.
2. Stage 2 invokes an external Agent CLI.
3. The Agent reads a skill and a previous stage artifact.
4. Stage 3 consumes the Agent's output and sends a PushPlus notification.

### 1.2 Scope

- **One demo pipeline**: `agent_demo.yaml`.
- **One Agent CLI preset**: `claude` (configurable to others).
- **One tool callback backend**: CLI wrapper (`python -m runtime.cli tool ...`).
- **One notification channel**: PushPlus. Telegram and Email are interface stubs only.
- **One skill**: `skills/core/agent_demo.md`.
- **No market-specific logic**: the demo uses a generic `demo_data_tool` that produces a JSON artifact.

### 1.3 Non-goals

- No `market_open_review` implementation.
- No MCP or HTTP backend implementation.
- No Telegram/Email notifier implementation.
- No position, memory, or trading tools.
- No management panel or approval workflow.

---

## 2. Demo Pipeline

File: `pipelines/agent_demo.yaml`

```yaml
name: agent_demo
version: "1.0"
description: Minimal demo of an Agent stage reading a previous artifact and producing output for a notification stage.
trigger:
  type: manual
stages:
  - name: generate_data
    tool: demo_data_tool
    inputs:
      topic: "BTC market outlook"

  - name: agent_analyze
    tool: agent_tool
    inputs:
      skill: "core/agent_demo"
      task_description: "Analyze the generated data and write a short report."
      timeout_sec: 120

  - name: notify
    tool: notify_tool
    inputs:
      subject: "Agent Demo Report"
      body: "$agent_analyze.summary"
      channels:
        - "pushplus"
```

Execution flow:

```text
run_pipeline("agent_demo")
  │
  ├── stage 1: generate_data
  │     tool: demo_data_tool
  │     output: artifacts/<run_id>/generate_data/demo_data.json
  │
  ├── stage 2: agent_analyze
  │     tool: agent_tool
  │     prompt references skill=skills/core/agent_demo.md
  │     prompt references artifact=artifacts/<run_id>/generate_data/demo_data.json
  │     Agent CLI reads skill and artifact
  │     Agent CLI writes report to artifacts/<run_id>/agent_analyze/report.md
  │     output: summary string + report artifact
  │
  └── stage 3: notify
        tool: notify_tool
        body resolved from $agent_analyze.summary
        only PushPlus sends; Telegram/Email stubs do nothing
```

---

## 3. Components

### 3.1 `demo_data_tool`

Location: `tools/demo/demo_data_tool.py`

A simple tool that produces a deterministic JSON artifact for the Agent to analyze.

Input schema:

```json
{
  "topic": "BTC market outlook"
}
```

Output schema:

```json
{
  "topic": "BTC market outlook",
  "rows": 3,
  "artifact": "demo_data.json"
}
```

Artifact `demo_data.json`:

```json
{
  "topic": "BTC market outlook",
  "data": [
    {"signal": "momentum", "value": 0.65},
    {"signal": "volume", "value": 0.42},
    {"signal": "sentiment", "value": 0.71}
  ]
}
```

### 3.2 `agent_tool`

Same interface as the full design, but scoped to the demo skill.

Input schema:

```json
{
  "skill": "core/agent_demo",
  "task_description": "Analyze the generated data and write a short report.",
  "timeout_sec": 120
}
```

Output schema:

```json
{
  "success": true,
  "report_artifact": "report.md",
  "summary": "The demo data shows positive momentum..."
}
```

### 3.3 `notify_tool`

Same interface as the full design, but only PushPlus is implemented.

Input schema:

```json
{
  "subject": "Agent Demo Report",
  "body": "The demo data shows positive momentum...",
  "channels": ["pushplus"]
}
```

Output schema:

```json
{
  "success": true,
  "results": {
    "pushplus": "ok",
    "telegram": "not_implemented",
    "email": "not_implemented"
  }
}
```

### 3.4 Agent Gateway

Same structure as the full design, but only the CLI backend is required.

- `runtime/agent_gateway/agent_driver.py`
- `runtime/agent_gateway/backends/base.py`
- `runtime/agent_gateway/backends/cli_backend.py`
- `runtime/agent_gateway/backends/mcp_backend.py` — raises `NotImplementedError`
- `runtime/agent_gateway/backends/http_backend.py` — raises `NotImplementedError`

### 3.5 Notifier Package

Only PushPlus is implemented. Other channels are no-op stubs.

- `runtime/notifier/base.py` — abstract `Notifier`
- `runtime/notifier/pushplus_notifier.py` — full implementation via `httpx`
- `runtime/notifier/telegram_notifier.py` — stub: `async def send(...): pass`
- `runtime/notifier/email_notifier.py` — stub: `async def send(...): pass`
- `runtime/notifier/composite.py` — `CompositeNotifier` + `build_notifier(config)` that only includes enabled channels

### 3.6 Skill

File: `skills/core/agent_demo.md`

```markdown
# agent_demo

## Goal
Read the data artifact from the previous stage and write a short analysis report.

## Tools you can use
- `demo_data_tool` (already ran in stage 1; read its artifact)
- `notify_tool(subject, body, channels)` — send the summary to PushPlus

## Inputs
- Pipeline run id: `{pipeline_run_id}`
- Previous stage artifact: `artifacts/{pipeline_run_id}/generate_data/demo_data.json`
- Output directory: `artifacts/{pipeline_run_id}/agent_analyze/`

## Output
Write a report to `artifacts/{pipeline_run_id}/agent_analyze/report.md` with:
1. A brief summary of the demo data.
2. Your interpretation.
3. A one-sentence notification summary.

Then call `notify_tool` with subject "Agent Demo Report", body set to your one-sentence summary, and channels `["pushplus"]`.

## Constraints
- Do not execute trades or call any unregistered tools.
```

---

## 4. CLI Extension

Same as full design:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json_string>'
```

This is the only tool callback backend implemented in the demo.

---

## 5. Configuration

`config.yaml` additions:

```yaml
agent:
  default_cli: "claude"
  custom_command: ""
  timeout_sec: 120
  max_iterations: 10
  tool_callback: "cli"
  headless_args:
    - "--allow-external"

mcp:
  enabled: false
  transport: "stdio"
  port: 8711

notifier:
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""
  pushplus:
    enabled: true
    token: ""   # set via QUANT_AGENT_NOTIFIER__PUSHPLUS__TOKEN
  email:
    enabled: false
    smtp_host: ""
    smtp_port: 465
    username: ""
    password: ""
    from_addr: ""
    to_addrs: []
```

---

## 6. Error Handling

| Scenario | Behavior |
|----------|----------|
| Agent CLI not installed | `agent_tool` fails; pipeline fails |
| Agent times out | Driver kills process; stage fails |
| Agent does not write `report.md` | Stage fails |
| PushPlus token missing | `notify_tool` returns `success=False`, result `"missing token"` |
| PushPlus API fails | Logged; `notify_tool` returns failure for that channel |
| Telegram/Email requested | Stubs return `"not_implemented"`; do not fail |

---

## 7. Testing Strategy

| Type | Test |
|------|------|
| Unit | `demo_data_tool` produces correct JSON artifact |
| Unit | `AgentDriver` constructs the correct CLI command from a mock config |
| Unit | `notify_tool` only calls PushPlus when configured |
| Integration | Run `agent_demo` pipeline with a fake Agent CLI script; assert `report.md` artifact exists and PushPlus notifier is called with the summary |

No live network calls. PushPlus API is mocked.

---

## 8. File Additions and Changes

### New files

```text
OpenQuantMaster/
├── runtime/agent_gateway/
│   ├── __init__.py
│   ├── agent_driver.py
│   ├── agent_task.py
│   ├── agent_result.py
│   └── backends/
│       ├── __init__.py
│       ├── base.py
│       ├── cli_backend.py
│       ├── mcp_backend.py
│       └── http_backend.py
├── runtime/notifier/
│   ├── __init__.py
│   ├── base.py
│   ├── composite.py
│   ├── pushplus_notifier.py
│   ├── telegram_notifier.py
│   └── email_notifier.py
├── tools/agent/
│   ├── __init__.py
│   └── agent_tool.py
├── tools/notifier/
│   ├── __init__.py
│   └── notify_tool.py
├── tools/demo/
│   └── demo_data_tool.py
├── skills/core/
│   └── agent_demo.md
├── pipelines/
│   └── agent_demo.yaml
└── tests/
    ├── runtime/test_agent_driver.py
    ├── runtime/test_notifier.py
    ├── tools/test_agent_tool.py
    ├── tools/test_notify_tool.py
    ├── tools/test_demo_data_tool.py
    └── integration/test_agent_demo_pipeline.py
```

### Modified files

- `pyproject.toml` — add `httpx`, `pydantic` already present.
- `runtime/config_loader.py` — add `AgentConfig`, `McpConfig`, notifier configs.
- `runtime/bootstrap.py` — initialize `AgentDriver` and `build_notifier`.
- `runtime/cli.py` — add `tool` subcommand.
- `AGENT_GUIDE.md` — mention `agent_demo` pipeline and `runtime/cli tool`.

---

## 9. Relationship to Full Design

This demo design is a **minimal slice** of `2026-07-19-agent-integration-design.md`. It intentionally leaves out:

- `market_open_review`
- Telegram/Email implementations
- MCP/HTTP backends
- `position_tool` / `read_memory_tool` stubs
- Multi-channel notifications

Once the demo is proven, the full design can be implemented by:

1. Replacing `agent_demo.yaml` with `market_open_review.yaml`.
2. Adding Telegram/Email notifier implementations.
3. Implementing MCP/HTTP backends.
4. Adding account/memory tool stubs.

---

## 10. Approval and Next Steps

This design proposes a minimal 3-stage `agent_demo` pipeline that:

- Generates demo data.
- Invokes an external Agent CLI to analyze it via a skill.
- Sends the summary through PushPlus.

**Next step**: invoke `superpowers:writing-plans` to produce the detailed implementation plan for this demo scope.
