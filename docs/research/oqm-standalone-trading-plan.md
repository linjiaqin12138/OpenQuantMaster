# OQM 独立交易方案实施计划（去 OpenAlice）

> 日期：2026-08-09。由 `docs/research/oqm-openalice-integration-plan.md` 派生——目标工作流不变，但移除对 OpenAlice 的全部依赖：新闻来源、决策 agent、交易执行全部收回 OQM 自实现。
> 前提变化：OQM 需要自行配置 Binance 凭证与风控（原方案"凭证单一事实源在 OpenAlice UTA"的架构决定整体反转）。

## 目标

两条工作流（与原方案相同）：

1. **定时研判（每小时）**：计算 K 线形态 + 技术指标，收集最近 1 小时新闻（含黑天鹅初筛），连同上下文交给本地 agent（claude/kimi headless）研判；agent 可查询仓位并（按模式）执行交易，结果经 PushPlus 通知用户。
2. **事件监控（高频）**：监控黑天鹅新闻、价格突破/跌破、订单状态变化，触发时立即唤起决策，并 PushPlus 通知。

## 架构总览（与原方案的对照）

| 层 | 原方案（OpenAlice 集成） | 本方案（独立） |
|---|---|---|
| 调度、数据采集、过滤、触发、通知 | OQM | OQM（不变） |
| 新闻原始归档（L0） | OpenAlice RSS 模块 | **OQM 自建 `rss_fetch_tool`**（feedparser + SQLite 归档），或第三方新闻 API |
| 语义研判、决策 | OpenAlice Pi agent（headless API） | **OQM 本地 `agent_tool`**（claude/kimi headless adapter，已存在） |
| 仓位/订单查询 | agent 侧 alice-uta | **新增 `account_tool`**（ccxt） |
| 交易执行 | alice-uta + allowAiTrading guards | **新增 `order_tool` + `risk_guard_tool`**（ccxt + 自研风控） |
| 人工审批 | OpenAlice git push 流程 | 无现成渠道（PushPlus 单向）——**起步走全自动 + 严格 risk guard** |
| 策略研究/回测（离线） | Vibe-Trading（vibe_tool） | 不变 |

## 现状盘点（OQM 侧）

可直接复用：

- cron 调度、顺序 pipeline + `$stage.field` 引用、artifact 落盘 + SQLite 状态存储（不变）
- `ohlcv_tool`（ccxt/binance 拉 K 线）、`indicator_tool`（TA-Lib 指标 + 形态）、`parallel_tool`（并行编排）、`notify_tool`（PushPlus）
- `news_filter_tool` 的 **LLM 评分部分**：litellm 批量评分、tenacity 重试、降级 PushPlus 告警、按 id 去重（`watch_state.json` 的 `news_filter.seen_ids`）、评分落 artifact——约 70% 逻辑原样保留
- `agent_tool` + `runtime/agent_gateway/adapters/`（claude / kimi / codex / generic 四个 headless adapter）——决策层的载体已存在
- `hourly_review.yaml` 的 context/notify 两个阶段结构
- watch_state.json 生命周期冷却状态机设计（见原方案专节，本方案原样沿用）

现状缺口 / 需改造（共 6 个新工具 + 3 个改造 + 2 个 pipeline + 配置）：

| 项 | 类型 | 说明 |
|---|---|---|
| `rss_fetch_tool` | 新 | RSS 采集 + SQLite 归档（替代 OpenAlice 新闻模块） |
| `news_filter_tool` | 改造 | 数据源从 OpenAliceClient 改为 NewsSource 接口 |
| `account_tool` | 新 | ccxt 查余额/仓位/挂单 |
| `order_tool` | 新 | ccxt 下/撤单（现货 + U 本位永续） |
| `risk_guard_tool` | 新 | 交易前风控检查（全自动模式唯一安全网） |
| `order_watch_tool` | 新 | ccxt 轮询挂单/成交，与快照 diff（原计划走 OpenAlice UTA，现改直连，反而更简单） |
| `price_watch_tool` / `event_trigger_tool` | 新 | 与原方案一致，不依赖 OpenAlice |
| `openalice_tool` / `runtime/openalice_client.py` | 删除 | 连同 `openalice:` 配置块与三个测试文件 |
| `hourly_review.yaml` / `event_watch.yaml` | 改造/新 | decide 阶段换本地 agent；新增事件监控 pipeline |

## 新闻架构（自建采集，替代 L0）

原方案"L0 = OpenAlice 归档、OQM 不自建采集"的结论作废。新三层：

**L0 原始归档 = `tools/news/rss_fetch_tool.py`（新）**：

- 实现：`feedparser` 拉取配置的 feed 列表（默认覆盖 CoinDesk / Cointelegraph / The Block + 宏观 Reuters/Fed），文章**含正文**直接写入 SQLite 归档表（复用 `data/runtime.db` 或独立 `data/news_archive.db`）：`articles(id, hash, feed, title, link, published_at, fetched_at, content)`，按 `hash`（title+link）唯一去重。
- 运行方式：**不需要常驻采集进程**——作为 pipeline 阶段被 cron 唤起。`event_watch.yaml`（`*/10`）里先于 `news_filter_tool` 跑一次 `rss_fetch_tool`，即可保证监控频率与归档新鲜度一致；`hourly_review` 同理。
- 配置：`config.yaml` 新增 `news: { feeds: [...], archive_db, retention_days: 7 }`。
- 已知上限与原方案相同：RSS 速度有限，黑天鹅由价格异动通道兜底。
- 备选：不想自建可用第三方 API（CryptoPanic / CryptoCompare News / GDELT 免费档 / 股票加 Finnhub）实现同一接口，免维护但有频率限制且无本地归档。

**接口抽象**：定义 `NewsSource` 协议（`fetch(from_time, limit) -> list[article]`，article 含 `id/time/title/source/link/content`）。`rss_fetch_tool` 的归档读取和第三方 API 各实现一个，`news_filter_tool` 只依赖接口。

**L1 叙事记忆**：`active-narratives.md` 从 OpenAlice workspace 挪到 OQM 侧 `data/agent_workspace/news/active-narratives.md`，prompt 契约不变（见「决策层」节）。

**L2 过滤与触发 = `news_filter_tool` 改造**：

- 删除 `OpenAliceClient` 依赖（`tools/news/news_filter_tool.py:125-135` 的 `window_rss` 调用和 `_enrich_article` 里的 `read_rss` 增强）：改为从本地归档读 `window_minutes` 增量；正文在采集时已落库，`_enrich_article` 整段删除。
- LLM 评分管线（prompt 模板、批量、tenacity 重试、失败 PushPlus 告警、`seen_ids` 去重、高中低三档分档、评分落 artifact）**全部保留不动**。
- 测试重写：mock OpenAlice gateway → mock NewsSource。

## 决策层（本地 agent 替代 openalice_tool）

decide 阶段从 `openalice_tool` 换成已有的 `agent_tool`（headless adapter）。关键差异与对策：

- **工具能力**：OpenAlice 的 agent 能调 alice-uta；OQM 的 agent 通过 `python -m runtime.cli tool <name> --inputs '<json>'` 调用本方案的 `account_tool` / `order_tool` / `risk_guard_tool`——决策 prompt 中明确给出这些命令和输入 schema。
- **session 连续性**：现有 adapter（claude/kimi/codex）**无 resume/session 机制**（grep 确认 adapter 层无 resume 支持）。两个选项：
  - A（推荐起步）：**无状态 + 文件记忆**。每次研判是独立 agent 调用，连续性完全靠 `active-narratives.md` 与 prompt 注入的上下文（指标、新闻、仓位）。实现零改动，代价是 agent 不记得上次对话细节——叙事文件已覆盖核心需求。
  - B：给 claude_adapter 加 `--resume <session_id>` 支持，session id 持久化到 `data/agent_session.json`（对应原方案的 `data/openalice_session.json`）。等无状态方案暴露记忆短板再做。
- **prompt 契约**：agent 的 workspace 为 `data/agent_workspace/`（git init 可选）；每次研判要求：1. 读/更新 `news/active-narratives.md`；2. 异动时查本地新闻归档回溯 24h~7d；3. 调 `account_tool` 查仓位挂单；4. 给出决策——执行前必须过 `risk_guard_tool`；5. 输出面向用户的一段中文总结。

## 交易工具（本方案最大新增量）

原方案明确排除的 `tools/account|execution|risk` 现在必须实现。**OQM 需自行持有 Binance 凭证**。

**配置**（`config.yaml` 新增，`runtime/config_loader.py` 加 `ExecutionConfig`）：

```yaml
execution:
  exchange: binance
  sandbox: true                # 起步必须 true（binance testnet）
  api_key: ""                  # env QUANT_AGENT_EXECUTION__API_KEY 注入
  api_secret: ""               # env QUANT_AGENT_EXECUTION__API_SECRET 注入
  default_market: futures      # U 本位永续 binanceusdm
risk:
  symbol_whitelist: ["SUI/USDT:USDT"]
  max_order_notional_usdt: 50
  max_position_notional_usdt: 200
  max_leverage: 3
  daily_loss_limit_usdt: 20
  order_cooldown_sec: 300
```

**`tools/account/account_tool.py`（新）**：ccxt `binanceusdm`（sandbox 走 testnet）查余额、仓位、挂单。输出结构化 JSON 落 artifact。替代原方案中 agent 侧 alice-uta 的查询职责。

**`tools/execution/order_tool.py`（新）**：下/撤单（现货 + U 本位永续，market/limit）。约束与原方案实测结论一致：**CCXT 不支持附带 TP/SL，止损必须分腿 reduceOnly 挂单**——写进工具输入契约（`stop_loss` 字段独立成单）与决策 prompt。默认 `dry_run: true`，显式 `dry_run: false` 才真实下单。

**`tools/risk/risk_guard_tool.py`（新，不可省略）**：交易前置检查，输入拟下单请求 + 当前账户状态，逐项校验：标的白名单、单笔/总仓名义上限、杠杆上限、日累计亏损熔断（从当日成交记录算）、下单冷却（`watch_state.json` 记录上次下单时间）。任一不过则拒绝并输出原因。**这是全自动模式唯一的安全网**——OpenAlice 的 guards 随集成一起消失。决策 prompt 强制约定：任何 `order_tool` 调用前必须先过 `risk_guard_tool`；`order_tool` 自身也内置一次 guard 调用兜底（不依赖 agent 自觉）。

**`tools/approval/`**：本期不实现。PushPlus 单向通知无法回批；起步模式 = **全自动 + 严格 risk guard + sandbox**。后续如需人工审批，做 CLI 命令（`quantmaster approve <proposal_id>`）+ pipeline 等待态，另立计划。

**`tools/research/order_watch_tool.py`（新）**：ccxt `fetch_open_orders` / `fetch_my_trades` 直连 Binance 轮询，与 `watch_state.json` 的 `orders_snapshot` diff，输出订单事件（新挂单/成交/撤单/部分成交）。比原方案走 OpenAlice UTA 代理更简单。

## 事件生命周期冷却与 watch_state.json

原方案专节设计**原样沿用**（new/developing/fading/resolved 状态机、升级判定、10 分钟全局节流、状态迁移与判定分离），不重述。`watch_state.json` 结构在原有基础上增加 `risk` 小节（`last_order_at`、`daily_realized_pnl`），供 `risk_guard_tool` 使用。

## Pipelines

**`pipelines/hourly_review.yaml`（改造）**，cron `3 * * * *`：

```yaml
stages:
  - context: parallel_tool
      calls:
        indicators:  { tool: indicator_tool,  inputs: {...} }
        news_fetch:  { tool: rss_fetch_tool,  inputs: { window_minutes: 70 } }
        news_digest: { tool: news_filter_tool, inputs: { window_minutes: 60 } }
        account:     { tool: account_tool,     inputs: {} }
  - decide: agent_tool          # prompt 模板注入 $context.*，契约见「决策层」节
  - notify: notify_tool         # body: $decide.summary, channels: [pushplus]
```

注：`news_fetch` 与 `news_digest` 串行依赖（先采集后过滤），若 parallel_tool 不支持阶段内依赖，则 `rss_fetch_tool` 提为独立前置 stage。

**`pipelines/event_watch.yaml`（新）**，cron `*/10 * * * *`：

```yaml
stages:
  - news_fetch: rss_fetch_tool      # 前置采集，保证归档新鲜
  - monitor: parallel_tool
      calls:
        price:  { tool: price_watch_tool, inputs: { symbols: ["SUI/USDT"] } }
        news:   { tool: news_filter_tool, inputs: { window_minutes: 20 } }
        orders: { tool: order_watch_tool, inputs: {} }
  - trigger: event_trigger_tool     # 内部唤起 agent_tool 决策（复用决策层）
      inputs: { price: "$monitor.price", news: "$monitor.news", orders: "$monitor.orders" }
  - notify: notify_tool             # 空 body 跳过（一行短路）
```

## 实施步骤

### Phase 0：凭证与连通性（约 0.5h）

1. 申请 Binance testnet API key/secret，配置 `QUANT_AGENT_EXECUTION__*` env。
2. 手动 python 验证 ccxt `binanceusdm` sandbox：fetch_balance / create_order / cancel。
3. 确认 PushPlus token 已配。

### Phase 1：新闻链路（2-3h）

1. `rss_fetch_tool` + SQLite 归档 + 单测（mock feedparser）。
2. `NewsSource` 接口 + `news_filter_tool` 改造（删 OpenAliceClient，删 `_enrich_article`）+ 测试重写。
3. `config.yaml` / `config_loader.py` 加 `news:` 块；feed 列表确认。

### Phase 2：交易链路（4-6h）

1. `ExecutionConfig` / `RiskConfig` 配置 + env 注入。
2. `account_tool` → `risk_guard_tool` → `order_tool`（顺序实现，后者依赖前者），各配单测（mock ccxt）。
3. `order_watch_tool` + 快照 diff 单测。
4. testnet 端到端：下单 → guard 拦截越界单 → order_watch 感知成交。

### Phase 3：决策层与 pipelines（2-3h）

1. `hourly_review.yaml` 改造（decide 换 `agent_tool`，prompt 契约含 cli 工具用法 + 叙事文件 + guard 约定）。
2. `event_watch.yaml` 新建（含 `price_watch_tool` / `event_trigger_tool`，与原方案 Phase 3 相同）。
3. `data/agent_workspace/` 初始化 + `active-narratives.md` 模板。

### Phase 4：删除清理与收尾（1-2h）

1. 删 `runtime/openalice_client.py`、`tools/agent/openalice_tool.py`、`config_loader.OpenAliceConfig`、`data/openalice_session.json` 逻辑、`tests/tools/test_openalice_tool.py`、`tests/runtime/test_openalice_client_conversation.py`、`tests/tools/test_news_filter_tool.py` 中的 gateway mock。
2. `config.yaml.example` / `.env.example` 补全 `news.*`、`execution.*`、`risk.*`。
3. `AGENTS.md` / `AGENT_GUIDE` / `oqm-tool` skill 更新工具清单。
4. 端到端：daemon 常驻 → 手动跑 hourly_review（确认叙事文件更新）→ 调低价格阈值构造事件触发 → 确认 PushPlus 通知 → testnet 小额单验证执行链路。

## 风险与注意事项

- **凭证安全**：Binance key 只走 env 注入，不落 git；`.env.example` 只放占位。API key 权限最小化（关提币，testnet 先行）。
- **全自动交易风险**：无人工审批环节，risk guard 是唯一防线——`order_tool` 内置 guard 兜底调用，不依赖 agent 自觉；起步 `sandbox: true` + 极小名义上限。
- **决策质量**：本地 headless agent（claude/kimi）无 resume 机制，上下文连续性全靠叙事文件 + prompt 注入；若实测发现跨周期记忆不足，再实现 adapter 的 `--resume` 支持（选项 B）。
- **RSS 时延**：与原方案相同，黑天鹅靠价格异动通道兜底，两条线都不可省略。
- **LLM 过滤器失败模式**：tenacity 重试后仍失败 → PushPlus 告警 + 价格异动通道值守，禁止 fail-open（沿用原方案）。
- **CCXT TP/SL 限制**：止损分腿 reduceOnly 挂单，写入 order_tool 契约与决策 prompt（原方案实盘实测结论，继续有效）。
- **sandbox 与生产差异**：testnet 撮合与资金费率和实盘有偏差，上实盘前需小资金验证。

## 工作量估算

| 项 | 估时 |
|---|---|
| Phase 0 凭证与连通性 | 0.5h |
| Phase 1 新闻链路（rss_fetch + news_filter 改造） | 2-3h |
| Phase 2 交易链路（account/risk_guard/order/order_watch） | 4-6h |
| Phase 3 决策层与 pipelines | 2-3h |
| Phase 4 删除清理 + 端到端 | 1-2h |
| **合计** | **10-15h** |

对照原方案：省掉了 Docker 网络/token 认证的坑和 OpenAlice 侧配置，多出了交易四件套与新闻自建采集；净增约 2-4h，换来零外部运行时依赖。
