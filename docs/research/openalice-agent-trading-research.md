# OpenAlice 自主交易 Agent 调研

> 调研日期：2026-07-26。基于 OpenAlice master @ `3fe61227`（0.84.0-beta），对照 `../quant/scripts/crypto_bot.py` 与 `../quant/watch_agent`。
> 目标问题：如何用 OpenAlice 承载「agent 自主并行搜新闻、算技术指标、按仓位决策」的交易工作流，以及事件驱动监控、纯 CLI 运作、自动交易、自定义执行层。

## 1. 范式差异：crypto_bot.py vs OpenAlice

### crypto_bot.py（`../quant/scripts/crypto_bot.py`，410 行）

- 单币种合约小时级机器人，核心类 `CryptoAgent`，交易对/资金/模型/周期全部硬编码在 `main()`。
- 流程是 4 个写死 prompt 的 LLM 线性流水线：技术分析 → 新闻分析 → 交易建议 → 执行方案 → 执行 agent 下单。
- 「并行」是假的：`get_operation_advice` 里 `t1.start(); t1.join(); t2.start(); t2.join()` 实际串行。
- LLM 输出为自由文本，无结构化校验；改流程必须改代码并重测。
- 同目录 `trade_agent_team.py` 更工程化（多 agent 团队 + 多空辩论 + XML 结构化决策），但流程仍是硬编码两段式。

### OpenAlice 的范式：文件即流程

- 进程内**没有 agent loop，也没有 workflow 引擎**（AGENTS.md 架构红线，`src/` 禁止长 workflow 引擎）。agent 运行时 = Claude Code / Codex / opencode / Pi 等原生 CLI。
- OpenAlice 提供三样东西：
  1. **Workspace**：git 化目录，agent 在其中读写文件、跑 CLI；
  2. **工具**：CLI shim（`alice`、`alice-uta`、`alice-workspace`、`traderhub`）+ MCP server，经 loopback HTTP 回 ToolCenter 执行；
  3. **Issue 调度**：`<workspace>/.alice/issues/<id>.md`，frontmatter 写 `when`（at/every/cron）+ `assignee`，正文即 prompt；`ScheduleScanner`（60s tick）到期后 headless 拉起 agent。
- 并行能力：原生 CLI 同轮并行 tool call；`conversation_ask`（全派发）+ `conversation_collect`（一次收集，内部 `Promise.all`）扇出/扇入；全局 headless 并发上限 `MAX_CONCURRENT_HEADLESS = 8`（`src/workspaces/service.ts:152`，超限 HTTP 429）。
- 调整工作流 = 改 markdown / SKILL.md，不改代码、无回归测试。

### 定时交易研判 issue 示例

```markdown
---
when: "0 * * * *"
assignee: @new
---
对 SUIUSDT 做本轮交易研判：
1. 并行：搜过去 1h 新闻并归纳情绪；算 1h(48根)/15m(16根) 的 SMA/MACD/RSI/BOLL/ATR；读账户仓位和保证金
2. 综合形成方向、仓位、止盈止损判断
3. 如需操作，stage + commit 交易提案
4. 推理和提案 inbox push 投递
```

## 2. 事件驱动监控（价格突破 / 黑天鹅新闻）

### 现状

- OpenAlice **刻意没有事件系统**：event bus / webhook 已退役（`docs/event-system.md` 明令禁止重建 dispatch）；`when` 只有 at/every/cron（`src/core/schedule-expr.ts:25`）；无价格预警/盯盘子系统。
- 官方认可的等价模式：cron issue + prompt 内自查条件 + 不满足静默退出（`docs/workspace-issues-and-scheduling.md:155-157`）。
- `../quant/watch_agent` 的现状正好互补：信号检测（MACD/RSI、Donchian 突破 + 去重）接近成品，但「信号 → LLM 决策 → 执行」是空壳（collectors/crews/executors 全传空 dict）。

### 推荐架构：外部 watcher + headless 唤起

```
[watcher 进程]                        [OpenAlice]
价格轮询(秒级)  ─┐
RSS 关键词初筛 ─┼─ 触发 ──► POST /api/workspaces/<wsId>/headless
(去抖+冷却)    ─┘                  { prompt: 事件上下文注入, resumeId }
                                       │
                                 agent 并行搜新闻/算指标/读仓位 → 决策 → 提案
```

- 唤起入口 `src/webui/routes/workspaces.ts:1794`，loopback 免认证，支持 `resumeId`（回到同一 Session，与定时分析共享记忆）和 `wait`（同步等结果）。
- watcher 职责：高频价格轮询、自己抓 RSS（绕开内置 collector——默认 10 分钟一轮且无入库钩子）、触发去重冷却（必须，否则打满 8 并发上限）。可复用 watch_agent 的信号检测与去重逻辑。
- 分层处置：确定性止损止盈别等 agent——挂券商侧条件单；agent 负责需要判断的部分（原因分析、加减仓、反向）。新闻侧用廉价关键词初筛，命中才唤起 LLM。
- 降级方案：`every: 1m` issue + prompt 自查，但每分钟一次完整 LLM run，只适合做原型。
- 歧路勿走：往 `.alice/issues/` 丢过期的 `at` 文件（~60s 延迟）；复活退役 event bus（违反架构红线）。

## 3. 纯 CLI 运作与自动交易

### 纯 CLI：可行

Web UI 只是 HTTP API 的客户端，loopback 免认证，curl 等价全部权限：

```bash
curl -fsSL https://openalice.ai/install | bash
openalice server start                                  # detached，不开浏览器（或 docker compose up -d）
curl -XPOST localhost:47331/api/config/credentials ...  # LLM API key
curl -XPOST localhost:47331/api/trading/config/uta ...  # 券商账户 + guards
curl -XPOST localhost:47331/api/workspaces -d '{"tag":"btc"}'
vim workspaces/btc/.alice/issues/premarket.md           # 手写 issue（官方认可）
curl localhost:47331/api/inbox/history                  # 读通知
```

- 无 systemd 支持；常驻靠 `openalice server start` 或 Docker（compose 已带 `restart: unless-stopped`）。
- 凭证必须走 API（`accounts.json` 是 AES-256-GCM sealed，不能手写明文）。
- agent runtime 若用订阅 OAuth 登录需一次浏览器配合；纯 API key 无此问题。

### 自动交易：`allowAiTrading` 开关（0.84 新增）

```bash
curl -XPUT localhost:47331/api/config/agent -d '{"allowAiTrading": true}'
```

- 默认 false，fail-closed，热读免重启（schema `src/core/config.ts:233-238`）。
- 开启后：agent 下单工具（带 `commitMessage`，stage+commit 一步）→ `tradingPush` → 直接 `uta.push()` 实盘发单（`src/tool/trading.ts:786-804`），**无任何人工环节**。
- 风控兜底：guards 三件套（`max-position-size` / `cooldown` / `symbol-whitelist`），按 UTA 账户配置；另有 per-account `readOnly: true` 硬闸门（对 AI push 同样生效）。

## 4. UTA「不稳定」的具体依据

UI 警告原文点名「**精度或参数问题**」，非套话：

1. **真实 bug 史**（`docs/uta-live-testing.md`，5 轮狗食约 20 个 bug）：19 位 orderId 被 float 截断导致撤单失效；附带 TP/SL 被 ccxt 静默丢弃、仓位裸奔（OKX 实测，事故注释留在 `CcxtBroker.ts:528-548`）；成本价错记；已平仓持仓残留显示。
2. **验收面窄**：真实券商 e2e 不在 CI（需 `OPENALICE_UTA_LIVE_PAPER=1`），S1–S14 目录只跑过 OKX / Bybit / Alpaca / IBKR paper 四家；其余 venue 视同未验收（Bybit 验收最充分）。
3. **订单状态同步薄弱**：纯轮询（pending 单 10s，慢车道 15min），无 WebSocket、无部分成交模型、有静默降级路径；push 后立即读成交不可靠（设计如此）。
4. **保护性订单缺口**：CCXT 全场拒绝附带 TP/SL 和追踪止损（`CcxtBroker.ts:538-584`）——自动交易止损只能分腿下单，裸仓位窗口真实存在。

## 5. 绕过 UTA：使用自定义执行工具

不改 OpenAlice 源码即可达成，三层组合：

1. **禁用内建 trading 工具**：`~/.openalice/data/config/tools.json` 的 `disabled` 逐个列 `trading*` 工具名（热读）。注意缺口：只过滤模型可见列表，`alice-uta` CLI 网关不查 disabled，不是硬墙。
2. **接入自定义工具（二选一）**：
   - **MCP server（推荐）**：workspace 根目录放 `.mcp.json` 指向自己的交易 MCP server；launcher 不写该文件，Claude adapter 带 `enableAllProjectMcpServers: true` 自动信任，headless 也生效。
   - **脚本/CLI**：`OPENALICE_EXTRA_AGENT_PATH` 加入 PATH（`src/workspaces/spawn-env.ts:141`）。坑：headless 下 Claude 只自动批准 `alice*`/`traderhub` Bash 前缀（`claude.ts:193-204`），自定义脚本会被挡；codex headless 无此限制。无人值守场景首选 MCP。
3. **引导 agent**：编辑 workspace `CLAUDE.md` + 自定义 `.claude/skills/*/SKILL.md`；或用 `AQ_TEMPLATES_DIR` 做 `injectTools: false` 的自定义模板，从创建起不注入 alice-uta 技能。

代价（需在自己的工具里重建）：guards 硬拦截、Trading-as-Git 审计链、人工审批门控。

### 推荐的最终形态

- **分析决策层全交给 OpenAlice**：定时 issue + watcher 事件唤起（带 `resumeId` 共享 Session）+ 并行工具调用；
- **执行层是自己的 MCP server**：封装 `../quant` 已验证的交易所 adapter + 自有止损/风控逻辑，避开 UTA 的 ccxt 短板；
- UTA 工具整体禁用；上线顺序：只读跑通链路 → demo 账户狗食 → 收紧 guards 上实盘。

## 关键文件索引（OpenAlice @ 3fe61227）

| 主题 | 位置 |
|---|---|
| 调度表达式 / scanner | `src/core/schedule-expr.ts`、`src/workspaces/schedule/scanner.ts`（60s tick） |
| 外部唤起 | `src/webui/routes/workspaces.ts:1794`（POST headless）、`src/webui/routes/inquiries.ts` |
| 认证（loopback 免密） | `src/webui/middleware/auth.ts:79-85` |
| 工具注册 / 禁用 | `src/core/tool-center.ts`、`src/main.ts:258-294`、`config.ts:388-391` |
| allowAiTrading | `src/core/config.ts:233-238`、`src/tool/trading.ts:786-804` |
| UTA guards | `services/uta/src/domain/trading/guards/`（registry.ts:7-9） |
| CCXT TP/SL 拒绝 | `services/uta/src/domain/trading/brokers/ccxt/CcxtBroker.ts:528-584` |
| 事件系统退役声明 | `docs/event-system.md` |
| issue/调度文档 | `docs/workspace-issues-and-scheduling.md` |
| UTA 狗食记录 | `docs/uta-live-testing.md` |
| spawn env / PATH | `src/workspaces/spawn-env.ts:70-164` |
| headless 权限白名单 | `src/workspaces/adapters/claude.ts:193-204` |
