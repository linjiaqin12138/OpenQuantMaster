# OpenQuantMaster — Agent Integration Design

## Document Control

- **Date**: 2026-07-19
- **Status**: Draft for review
- **Author**: Claude Code (collaborative session with project owner)
- **Related documents**:
  - `docs/superpowers/specs/2026-07-12-agent-trading-system-design.md` (system design)
  - `docs/superpowers/specs/2026-07-16-agent-trading-milestone2-design.md` (M2 design)
  - `docs/superpowers/plans/2026-07-19-agent-trading-milestone3-plan.md` (M3 plan)
- **Decision**: Add an **Agent Gateway** to OpenQuantMaster that supports external Agent CLIs (Claude Code, Codex, Kimi CLI, etc.) as the analysis/decision plane. Tool callbacks default to a CLI wrapper, with optional MCP and HTTP backends.

---

## 1. Purpose and Scope

### 1.1 Problem Statement

Milestone 2 gives the runtime real market-data and research tools, but pipelines such as `market_open_review` stop after fetching OHLCV. There is no component that:

- invokes an LLM Agent to analyze pipeline outputs,
- lets the Agent autonomously look up additional context (positions, memory, news),
- turns the analysis into a user-facing notification.

This design closes that gap.

### 1.2 Goals

1. **Scheduled Agent**: cron-triggered pipelines can spawn an external Agent CLI at a specific stage to analyze results and produce a report.
2. **Interactive Agent**: a user in the workspace can ask an Agent CLI to research a topic; the Agent reads skills and calls tools directly.
3. **Agent-agnostic interface**: Claude Code, Codex, Kimi CLI, OpenClaw, Hermes, or any other programming-assistant CLI can operate the system through the same `AGENT_GUIDE.md`, skills, and tool schemas.
4. **Unified tool callback model**: the runtime exposes tools to Agents through three backends, defaulting to a simple CLI wrapper, with optional MCP and HTTP APIs.
5. **Notifications**: Agent-generated reports can be sent through Telegram, PushPlus, and Email.

### 1.3 Non-goals

- **No trade execution in this batch**. The Agent may recommend trades, but it cannot submit paper or live orders.
- **No human-approval workflow**. That belongs to M3.
- **No management panel**. That belongs to M3.
- **No full-auto mode**. Every scheduled run is analysis/notification only.

---

## 2. Design Principles

1. **Agent reads skills; code does not construct data**. The runtime passes the Agent a task description and a skill reference. The Agent is responsible for reading the skill file and using the documented tools to fetch market data, positions, and memory.
2. **Workspace is the project directory**. The Agent CLI runs with the OpenQuantMaster project root as its working directory so it can read `AGENT_GUIDE.md`, `skills/`, `config.yaml`, and `artifacts/` directly.
3. **Tool invocation is backend-pluggable**. The default CLI wrapper works with any Agent CLI that can run shell commands. MCP and HTTP backends are supported for better integration when available.
4. **Fail-safe notifications**. A notification-channel failure is logged but never fails a pipeline stage.
5. **Re-use M3 building blocks**. The notifier package introduced here is intentionally aligned with the M3 notifier design so it can be reused for approval notifications later.

---

## 3. High-level Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                    External Agent CLI                               │
│   Claude Code / Codex / Kimi CLI / OpenClaw / Hermes                │
│       reads: AGENT_GUIDE.md → skills/trading/*.md                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  spawn headless CLI / MCP / HTTP
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     OpenQuantMaster Runtime                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │  Scheduler  │  │   Pipeline   │  │       Agent Gateway       │  │
│  │             │──▶│   Runner     │──▶│  ┌─────────────────────┐  │  │
│  │             │  │              │  │  │    AgentDriver      │  │  │
│  │             │  │              │  │  │ ┌─────┐ ┌─────┐     │  │  │
│  │             │  │              │  │  │ │ CLI │ │ MCP │     │  │  │
│  │             │  │              │  │  │ │(def)│ │     │     │  │  │
│  │             │  │              │  │  │ └─────┘ └─────┘     │  │  │
│  │             │  │              │  │  │ ┌─────┐             │  │  │
│  │             │  │              │  │  │ │ HTTP│             │  │  │
│  │             │  │              │  │  │ └─────┘             │  │  │
│  └─────────────┘  └──────────────┘  │  └─────────────────────┘  │  │
│                                     └───────────────────────────┘  │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │  StateStore │  │  Event Bus   │  │        Notifier           │  │
│  │             │  │              │  │  Telegram / PushPlus /    │  │
│  │             │  │              │  │  Email                    │  │
│  └─────────────┘  └──────────────┘  └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
                    ┌───────────────┐
                    │     tools/    │
                    │  ohlcv_tool   │
                    │ position_tool │
                    │ read_memory   │
                    │  notify_tool  │
                    │   agent_tool  │
                    └───────────────┘
```

---

## 4. Components

### 4.1 Agent Gateway

Location: `runtime/agent_gateway/`

Responsibilities:

- Prepare a task prompt and working directory for an external Agent CLI.
- Spawn the configured CLI with the correct flags.
- Collect the Agent's output artifacts.
- Expose three tool-callback backends so the Agent can call runtime tools.

#### 4.1.1 `AgentDriver`

```python
class AgentDriver:
    def __init__(self, config: RuntimeConfig, registry: ToolRegistry, store: StateStore) -> None: ...

    async def run(self, task: AgentTask) -> AgentResult:
        """Spawn the configured Agent CLI and return its output."""
```

`AgentTask`:

```python
@dataclass
class AgentTask:
    skill: str                        # e.g. "trading/market_open_review"
    task_description: str             # human-readable task
    pipeline_run_id: uuid.UUID | None
    stage_name: str | None
    output_dir: Path
    timeout_sec: int = 300
    max_iterations: int = 10
```

`AgentResult`:

```python
@dataclass
class AgentResult:
    success: bool
    report_path: Path | None
    summary: str
    tool_calls: list[dict[str, Any]]
    error: str | None
```

#### 4.1.2 Working Directory

`AgentDriver` spawns the Agent CLI with the OpenQuantMaster project root as its current working directory. The project root is derived from `config.config_path.parent` when a config file is loaded, or falls back to the process current working directory.

This lets the Agent CLI read `AGENT_GUIDE.md`, `skills/`, `config.yaml`, and `artifacts/` directly without copying anything into a task workspace.

#### 4.1.3 Supported Agent CLIs

The driver supports a configurable CLI command. Built-in presets:

| Preset | Command |
|--------|---------|
| `claude` | `claude -p "{prompt}" {headless_args}` |
| `codex` | `codex -a "{prompt}" {headless_args}` |
| `kimi` | `kimi -p "{prompt}" {headless_args}` |
| `custom` | `config.agent.custom_command` |

The exact flags are left to the preset mapping because different CLIs use different headless options. The configuration section allows arbitrary extra headless arguments. Flags such as `--allow-external` are Agent-CLI-specific; the user is responsible for choosing safe headless arguments for their installed CLI.

### 4.2 Tool Callback Backends

Location: `runtime/agent_gateway/backends/`

All backends share the same interface:

```python
class ToolBackend(ABC):
    @abstractmethod
    async def call(self, tool_name: str, inputs: dict[str, Any]) -> ToolResult: ...
```

#### 4.2.1 CLI Backend (default)

The Agent CLI invokes tools as a subprocess:

```bash
python -m runtime.cli tool ohlcv_tool \
  --inputs '{"symbol":"000001.SZ","market":"a_share","interval":"1d"}'
```

The CLI writes JSON to stdout:

```json
{
  "success": true,
  "data": {"symbol": "000001.SZ", "rows": 60, "artifact": "ohlcv_000001.SZ_1d.csv"},
  "artifacts": [...],
  "error": null
}
```

Implementation notes:

- `runtime/agent_gateway/backends/cli_backend.py` implements the in-process tool execution logic.
- `runtime/cli.py tool ...` is the CLI entry point that loads config, discovers tools, invokes `CliBackend.call(...)`, and prints the `ToolResult` JSON.
- The Agent CLI sees `python -m runtime.cli tool ...` as a normal shell command it can execute.

#### 4.2.2 MCP Backend

The runtime exposes an MCP server (`runtime/agent_gateway/backends/mcp_server.py`) that registers every discovered `BaseTool` as an MCP tool.

- Transport: `stdio` or `sse`.
- Configuration: `mcp.enabled`, `mcp.transport`, `mcp.port`.
- The Agent CLI connects via its own MCP client configuration (e.g., Claude Code `--mcp-config`).

This backend is **not implemented in the first batch**; the interface exists and raises `NotImplementedError` cleanly.

#### 4.2.3 HTTP Backend

A FastAPI application exposes tools under `/api/v1/tools/{tool_name}`. This reuses the runtime API work from M3.

- Request: `POST /api/v1/tools/{tool_name}` with JSON body.
- Response: same JSON shape as CLI backend.

This backend is **not implemented in the first batch**; the interface exists and raises `NotImplementedError` cleanly.

### 4.3 `agent_tool`

Location: `tools/agent/agent_tool.py`

A `BaseTool` that pipeline stages can call to invoke an Agent analysis.

Input schema:

```json
{
  "skill": "trading/market_open_review",
  "task_description": "请基于 skill 做 A 股开盘分析",
  "timeout_sec": 300,
  "max_iterations": 10
}
```

Output schema:

```json
{
  "success": true,
  "report_artifact": "market_open_review_report.md",
  "summary": "Agent 认为今日...",
  "tool_calls_count": 5
}
```

Behavior:

1. Resolve the skill path (`skills/trading/market_open_review.md`).
2. Create an output directory under `artifacts/<run_id>/<stage_name>/`.
3. Build a prompt that references the skill and the current pipeline run artifacts.
4. Call `AgentDriver.run(task)`.
5. Persist `report.md` as an artifact.
6. Return metadata and summary.

### 4.4 `notify_tool`

Location: `tools/notifier/notify_tool.py`

A `BaseTool` that sends notifications through configured channels.

Input schema:

```json
{
  "subject": "A股开盘Review",
  "body": "Agent分析认为...",
  "channels": ["telegram", "pushplus", "email"]
}
```

Output schema:

```json
{
  "success": true,
  "results": {
    "telegram": "ok",
    "pushplus": "ok",
    "email": "channel down"
  }
}
```

Behavior:

- Fan out to each requested channel independently.
- A channel failure is logged and returned in `results`, but the tool still returns `success=True` unless all channels fail.
- If `channels` is omitted, use all enabled channels from config.

### 4.5 Notifier Package

Location: `runtime/notifier/`

Aligned with the M3 notifier design:

- `base.py`: `Notifier` abstract class.
- `telegram_notifier.py`: Telegram Bot API via `httpx`.
- `pushplus_notifier.py`: PushPlus API via `httpx`.
- `email_notifier.py`: SMTP via `aiosmtplib`.
- `composite.py`: `CompositeNotifier` that isolates channel failures; `build_notifier(config)`.

### 4.6 Skill for `market_open_review`

Location: `skills/trading/market_open_review.md`

The skill is the single source of truth for what the Agent should do. It documents:

- The goal (A-share morning review).
- Available tools and their schemas.
- Expected output format.
- Constraints (no trading in this batch).

Example:

```markdown
# market_open_review

## Goal
After the A-share market opens, analyze the watch-list symbols and produce a short morning review.

## Tools you can use
- `ohlcv_tool(symbol, market, interval, start, end)` — fetch OHLCV.
- `position_tool()` — query current positions. *(First batch: returns empty list.)*
- `read_memory_tool(topic, symbol, limit)` — query historical memory. *(First batch: returns empty list.)*
- `notify_tool(subject, body, channels)` — send the report to the user.

## Inputs available in this run
- Pipeline run id: `{pipeline_run_id}`
- Previous stage artifact: `artifacts/{pipeline_run_id}/fetch_watchlist_ohlcv/`

## Output
Write a report to `artifacts/{pipeline_run_id}/analyze_with_agent/market_open_review_report.md` containing:
1. Market snapshot
2. Key technical levels
3. Comparison with recent memory
4. Today's view (watch / caution / alert)
5. Risk note

## Constraints
- Do NOT execute trades in this batch.
- If uncertain, say so explicitly.
```

### 4.7 Minimal Tool Stubs

The system design calls for `position_tool` and `read_memory_tool`, but these are not implemented in M2 and will be implemented more fully in later milestones. To keep the `market_open_review` skill stable and let the Agent invoke a consistent interface, this batch introduces minimal stubs:

- `tools/account/position_tool.py` — returns an empty position list and zero PnL.
- `tools/memory/read_memory_tool.py` — returns an empty memory list.

These stubs have real input/output schemas and are registered in the tool registry. The Agent can call them; in this batch they simply return "no positions" / "no memory". Later milestones will replace the stub implementations without changing the tool contract.

---

## 5. Data Flow

### 5.1 Scheduled `market_open_review` with Agent

```text
cron 09:00 Asia/Shanghai
  │
  ▼
APSchedulerAdapter fires
  │
  ▼
PipelineRunner.run_pipeline("market_open_review")
  │
  ├── stage 1: fetch_watchlist_ohlcv
  │     tool: ohlcv_tool
  │     inputs: symbol=000001.SZ, market=a_share, interval=1d
  │     output: artifacts/<run_id>/fetch_watchlist_ohlcv/ohlcv_000001.SZ_1d.csv
  │
  ├── stage 2: analyze_with_agent
  │     tool: agent_tool
  │     inputs:
  │       skill: "trading/market_open_review"
  │       task_description: "A-share morning review"
  │     behavior:
  │       1. AgentTool builds AgentTask
  │       2. AgentDriver spawns configured CLI with prompt referencing skill
  │       3. Agent CLI reads skill
  │       4. Agent CLI calls tools via CLI backend
  │       5. Agent CLI writes report to artifacts/<run_id>/analyze_with_agent/
  │     output: artifacts/<run_id>/analyze_with_agent/market_open_review_report.md
  │
  └── stage 3: notify
        tool: notify_tool
        inputs:
          subject: "A-share morning review"
          body: "$analyze_with_agent.summary"
          channels: ["telegram", "pushplus", "email"]
        output: notification results
```

### 5.2 Interactive Research Agent

```text
User in workspace:
  "帮我看看最近 30 天 BTC 的走势，并和上次 memory 里的观点对比"
  │
  ▼
Agent CLI reads AGENT_GUIDE.md and skills/trading/research_skill.md
  │
  ▼
Agent CLI calls tools directly through CLI backend:
  python -m runtime.cli tool ohlcv_tool --inputs '{...}'
  python -m runtime.cli tool read_memory_tool --inputs '{...}'
  │
  ▼
Agent CLI produces report / answer in workspace
```

No pipeline runner is involved in the interactive path. The Agent CLI is the orchestrator and the runtime tools are its primitives.

---

## 6. Prompt Construction

The runtime does **not** embed market data, positions, or memory in the prompt. The prompt is a task envelope:

```markdown
You are an A-share market analysis assistant.

Current task:
- Skill: skills/trading/market_open_review.md
- Pipeline run id: {pipeline_run_id}
- Previous stage artifact directory: artifacts/{pipeline_run_id}/fetch_watchlist_ohlcv/
- Output directory: artifacts/{pipeline_run_id}/analyze_with_agent/

Instructions:
1. Read the skill file to understand the task and available tools.
2. Use the tools to fetch any data you need (OHLCV, positions, memory, etc.).
3. Write your analysis to {output_dir}/market_open_review_report.md.
4. After writing the report, call notify_tool to send the summary to the user.

Constraints:
- Do not execute trades.
- If you are uncertain, state it clearly.
- All tool calls should go through: python -m runtime.cli tool <tool_name> --inputs '<json>'
```

This keeps the runtime generic and puts domain knowledge in the skill file.

---

## 7. Configuration

### 7.1 New `config.yaml` sections

```yaml
agent:
  default_cli: "claude"           # claude | codex | kimi | openclaw | hermes | custom
  custom_command: ""              # used when default_cli is "custom"
  timeout_sec: 300
  max_iterations: 10
  tool_callback: "cli"            # cli | mcp | http
  headless_args:
    - "--allow-external"

mcp:
  enabled: false
  transport: "stdio"              # stdio | sse
  port: 8711

notifier:
  telegram:
    enabled: false
    bot_token: ""
    chat_id: ""
  pushplus:
    enabled: false
    token: ""
  email:
    enabled: false
    smtp_host: ""
    smtp_port: 465
    username: ""
    password: ""
    from_addr: ""
    to_addrs: []
```

### 7.2 `RuntimeConfig` extensions

Add Pydantic models:

- `AgentConfig`
- `McpConfig`
- `TelegramConfig`
- `PushplusConfig`
- `EmailConfig`
- `NotifierConfig`

Update `RuntimeConfig` with:

```python
agent: AgentConfig = Field(default_factory=AgentConfig)
mcp: McpConfig = Field(default_factory=McpConfig)
notifier: NotifierConfig = Field(default_factory=NotifierConfig)
```

---

## 8. CLI Extension

Add a subcommand to `runtime/cli.py`:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json_string>'
```

Behavior:

1. Load config and bootstrap the tool registry (no scheduler, no runner).
2. Parse `--inputs` as JSON.
3. Look up the tool by name.
4. Execute the tool.
5. Print `ToolResult` JSON to stdout.

This is the mechanism the CLI backend uses. It must be usable both inside the daemon's virtualenv and from an Agent CLI spawned in the same project directory.

---

## 9. Error Handling

| Scenario | Behavior |
|----------|----------|
| Configured Agent CLI not installed | `agent_tool` returns failure; pipeline stage fails; event logged |
| Agent process times out | Driver kills process; stage fails; report partial output if available |
| Agent calls an unknown tool | CLI backend returns `ToolNotFoundError`; Agent sees it and can retry |
| Tool execution fails | Error returned to Agent in `ToolResult.error` |
| Agent does not write report | Stage fails with clear message |
| All notification channels fail | `notify_tool` returns `success=False` but does not fail pipeline (configurable) |
| Single notification channel fails | Logged; other channels continue |
| Agent attempts to call a trading tool | Tool not registered in first batch; call fails |

---

## 10. Security and Safety

1. **Tool sandboxing**: the CLI backend only executes registered `BaseTool` instances; arbitrary shell commands are not allowed.
2. **No live trading**: `paper_trade_tool` and `live_trade_tool` are not registered in this batch.
3. **Secrets**: notifier credentials live in `.env` / `config.yaml` and are never committed.
4. **Agent headless args**: `headless_args` is configurable; defaults should not include dangerous flags.
5. **Timeout**: every Agent invocation has a hard timeout to prevent runaway processes.

---

## 11. Testing Strategy

| Type | Coverage |
|------|----------|
| Contract | `agent_tool` and `notify_tool` input/output schemas; pipeline manifest schema still validates `market_open_review` |
| Unit — `AgentDriver` | Mock CLI subprocess; assert correct command construction and output parsing |
| Unit — CLI backend | Assert `python -m runtime.cli tool ...` executes the right tool and returns JSON |
| Unit — notifier | Mock Telegram/PushPlus/Email APIs; assert CompositeNotifier isolates failures |
| Unit — config | Assert new `agent`, `mcp`, `notifier` sections load with defaults |
| Integration | Run `market_open_review` with fake `ohlcv_tool` and a fake Agent CLI script; assert report artifact exists and notification is attempted |
| Preflight | `make preflight` prints configured Agent CLI, tool callback backend, and enabled notifier channels |

No live network calls in CI. Agent CLI, Telegram, PushPlus, and SMTP are all mocked.

---

## 12. File Additions and Changes

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
│   ├── telegram_notifier.py
│   ├── pushplus_notifier.py
│   └── email_notifier.py
├── tools/agent/
│   ├── __init__.py
│   └── agent_tool.py
├── tools/notifier/
│   ├── __init__.py
│   └── notify_tool.py
├── tools/account/
│   └── position_tool.py
├── tools/memory/
│   └── read_memory_tool.py
├── skills/trading/
│   └── market_open_review.md
└── tests/
    ├── runtime/test_agent_driver.py
    ├── runtime/test_notifier.py
    ├── runtime/test_config_loader_agent.py
    ├── tools/test_agent_tool.py
    ├── tools/test_notify_tool.py
    ├── tools/test_position_tool.py
    ├── tools/test_read_memory_tool.py
    └── integration/test_market_open_review_agent.py
```

### Modified files

- `pyproject.toml` — add `httpx`, `aiosmtplib` and other notifier/runtime dependencies.
- `runtime/config_loader.py` — add `AgentConfig`, `McpConfig`, notifier configs to `RuntimeConfig`.
- `runtime/bootstrap.py` — initialize `AgentDriver` and composite notifier; wire tool backend.
- `runtime/cli.py` — add `tool` subcommand.
- `pipelines/market_open_review.yaml` — add `analyze_with_agent` and `notify` stages.
- `AGENT_GUIDE.md` — mention Agent Gateway and the `runtime/cli tool` command.

---

## 13. Relationship to M3

This design is an **Agent-enablement layer between M2 and M3**:

- Reuses the M2 runtime, tool registry, and pipeline runner.
- Introduces the notifier package that M3 will use for approval notifications.
- Does not implement M3's `decision_tool`, `paper_trade_tool`, approval workflow, or panel.
- Once M3 is implemented, the Agent can call `decision_tool` to produce `TradeDecision` objects and enter the approval flow.

---

## 14. Approval and Next Steps

This design proposes adding an Agent Gateway to OpenQuantMaster that:

- Lets external Agent CLIs analyze pipeline outputs via skills.
- Defaults to a CLI-wrapper tool callback and reserves MCP/HTTP backends.
- Adds notification support (Telegram, PushPlus, Email).
- Keeps the first batch analysis-only (no trade execution).
- Demonstrates the end-to-end flow in an enhanced `market_open_review` pipeline.

**Next step**: invoke `superpowers:writing-plans` to produce the detailed implementation plan.
