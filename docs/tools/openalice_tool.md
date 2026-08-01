# openalice_tool

`openalice_tool` invokes the OpenAlice agent runtime through the **CLI gateway** — OpenAlice's machine-facing surface — using the `conversation_ask` tool from the gateway's `workspace` export. This is the same channel `news_filter_tool` uses for RSS (`data` export), just a different export segment in the URL.

Under the hood, `conversation_ask` dispatches a headless agent turn through the exact same pipeline as OpenAlice's own scheduler and web UI (`dispatchHeadlessTask`), with first-class session addressing: pass a `resumeId` to continue an existing agent conversation, or a `wsId` to recruit a fresh worker in a workspace.

Session continuity: after each successful call the tool persists the returned `resumeId` to `data/openalice_session.json` (per workspace) and sends it on the next call. If the server reports the stored session as gone (`status: "unavailable"`), the tool drops it and retries once as a fresh session.

## Dependencies

- `httpx` — async HTTP client (already a main dependency).
- `structlog`, `pydantic` — already part of the runtime.

No new dependencies, no authentication: the CLI gateway is open posture by design ("no admin-token gate — the workspace CLI carries no secret").

> **Security note**: the gateway is unauthenticated. If the OpenAlice container publishes ports `47332-47335` on `0.0.0.0`, any host on the network can drive the agent (and trade, when `allowAiTrading` is on). Bind the published ports to `127.0.0.1` in the compose file.

## Configuration

```yaml
openalice:
  workspace_id: auto-quant-clear-willow-field
  cli_gateway_url: http://127.0.0.1:47332
  export: data            # used by news_filter_tool; openalice_tool always uses the `workspace` export
  default_timeout: 300    # seconds; server caps timeoutMs at 1800
```

All fields can be overridden via env vars, e.g. `QUANT_AGENT_OPENALICE__WORKSPACE_ID`, `QUANT_AGENT_OPENALICE__CLI_GATEWAY_URL`.

## Input parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | yes | — | Prompt for the agent. Truncated to 16000 chars (server-enforced limit); `truncated` flags when this happens. |
| `wait` | boolean | no | `true` | `true`: server waits for the run to finish (`await:true`) and the reply is returned in one call. `false`: return immediately after dispatch with `status="running"`. |
| `timeout_sec` | integer | no | `openalice.default_timeout` (300) | Server-side run watchdog (`timeoutMs`), max 1800. |
| `resume` | boolean | no | `true` | `true`: continue the persisted session (if any). `false`: always start a fresh conversation. |
| `pipeline_run_id` | string | no | `null` | Auto-injected by the pipeline runner; unused by this tool. |

## Output structure

On success, `ToolResult.data` contains:

```json
{
  "success": true,
  "response": "Agent's final assistant text (empty when wait=false)",
  "session_id": "<resumeId — reused automatically on the next call>",
  "task_id": "<headless task id>",
  "status": "done",
  "truncated": false
}
```

- `response` — the agent's final assistant text (`assistantText` from the task projection).
- `session_id` — the OpenAlice `resumeId`; persisted automatically, useful for debugging.
- `task_id` — the headless task id (inspect via `alice-workspace conversation read --task-id <id>` inside the container).
- `status` — `done` after a waited run, `running` when `wait=false`.
- `truncated` — `true` when the prompt exceeded 16000 chars and was cut.

## Session file

`data/openalice_session.json`, keyed by workspace id so multiple workspaces don't clobber each other:

```json
{
  "auto-quant-clear-willow-field": {
    "resume_id": "abc123",
    "updated_at": "2026-07-29T14:00:00Z"
  }
}
```

Written atomically (tmp + replace). A corrupt file is treated as empty. Memory continuity across a session rebuild is the agent's workspace files (e.g. `news/active-narratives.md`), not this file — see the integration plan.

## Error handling

- **Session gone** (`{"ok": false, "status": "unavailable"}`, e.g. `missing-session` / `retired-session`) — the stored `resumeId` is discarded and the prompt is retried once as a fresh session (`wsId` target).
- **Task failed** (`ok` but `status` is `failed` / `interrupted`) — `success=False` with the server-provided `error`; the session file is left untouched.
- **Rejected** (`ok: false` with `error`, e.g. capacity limit 8 reached, conversation busy) — `success=False`, no retry.
- **Gateway unreachable / malformed response** — `success=False` with the transport error.

## CLI usage examples

### 1. Blocking invocation with a custom timeout

```bash
python -m runtime.cli tool openalice_tool \
  --inputs '{"prompt": "综合研判当前仓位并给出操作建议", "timeout_sec": 600}'
```

### 2. Fire-and-forget dispatch

```bash
python -m runtime.cli tool openalice_tool \
  --inputs '{"prompt": "用 alice-uta 查询当前账户概况并总结", "wait": false}'
```

### 3. Start a fresh conversation (ignore stored session)

```bash
python -m runtime.cli tool openalice_tool \
  --inputs '{"prompt": "重新开始：总结最近 24 小时的持仓变化", "resume": false}'
```

## Pipeline YAML example

```yaml
stages:
  - decide:
      tool: openalice_tool
      inputs:
        prompt: "请读取 news/active-narratives.md，结合最新仓位给出研判总结。"
        timeout_sec: 600
  - notify:
      tool: notify_tool
      inputs:
        subject: "OpenAlice 研判"
        body: "$decide.out.response"
        channels: [pushplus]
```

## Notes

- The gateway contract was verified against the OpenAlice source (`src/server/cli.ts`, `src/tool/conversation.ts`, `src/workspaces/conversation-control.ts`): `conversation_ask` and the web UI's headless route converge on the same `dispatchHeadlessTask`, so capacity limits, the 16000-char prompt cap, and the 1800s timeout cap apply identically.
- Concurrent invocations on the *same* session are rejected by the server (conversation busy) — serialize calls that share the persisted session.
- The gateway response is an MCP-style envelope (`content[0].text` holds the JSON payload); `OpenAliceClient.invoke()` unwraps it.
