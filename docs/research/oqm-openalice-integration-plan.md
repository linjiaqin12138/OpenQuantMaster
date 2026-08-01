# OQM × OpenAlice 集成实施计划

> 日期：2026-07-26。前置调研见 `docs/research/openalice-agent-trading-research.md`。
> 环境：OpenAlice 运行在 docker 容器 `openalice`（Pi 作为 agent runtime，已配置 Binance 账户）；OpenQuantMaster（OQM）跑在宿主机；用户通知仅支持 PushPlus。

## 目标

两条工作流：

1. **定时研判（每小时）**：计算 K 线形态 + 技术指标，收集最近 1 小时新闻（含黑天鹅初筛），连同上下文交给 OpenAlice 的 Pi agent，由它结合 Binance 仓位自主决策并（按配置）执行，结果经 PushPlus 通知用户。
2. **事件监控（高频）**：监控黑天鹅新闻、价格突破/跌破、订单状态变化，触发时立即唤起 OpenAlice 决策，并 PushPlus 通知。

## 分工原则

| 层 | 承担方 | 理由 |
|---|---|---|
| 调度、数据采集、廉价过滤（代码 + 廉价 LLM）、触发、通知 | **OQM** | cron 调度/顺序 pipeline/PushPlus 已成品；过滤层用 gpt-4o-mini 级模型，日成本 < ¥0.1 |
| 语义研判、仓位感知决策、交易执行 | **OpenAlice** | Pi agent + alice-uta（Binance 已在其中配置，仓位/订单单一事实源在 UTA） |
| 策略研究/回测（离线） | **Vibe-Trading（vibe_tool）** | 不在实时链路；用于上线前验证指标参数和策略逻辑 |

关键架构决定：**OQM 不重复配置 Binance 凭证**。定时研判中，仓位/订单由 OpenAlice agent 自己在容器内用 `alice-uta` 查询；事件监控中的订单状态检查走 OpenAlice 的 UTA HTTP API 代理查询。OQM 侧 `tools/account/`、`tools/execution/` 空目录本期不实现。

## 现状盘点（OQM 侧）

可直接复用：

- cron 调度（APScheduler 4.x，5 段 cron，daemon 常驻扫 `pipelines/*.yaml`）
- 顺序 pipeline + `$stage.field` 引用（无并行/条件分支——把条件逻辑收进单个 tool 内部短路，不改 runner）
- `ohlcv_tool`：ccxt/binance 拉 K 线，输出 CSV artifact
- `notify_tool` → PushplusNotifier **已实现**（真实 POST pushplus.plus），`agent_demo.yaml` 已演示完整通知链路
- artifact 落盘 + sha256 + SQLite 状态存储、checkpoint
- `agent_demo.yaml` 是最接近目标的模板（data → agent → notify）

缺口（全部需新写，共 5 个工具 + 2 个 pipeline + 配置）：

| 缺口 | 说明 |
|---|---|
| `indicator_tool` | 技术指标（SMA/EMA/MACD/RSI/BOLL/ATR）+ K 线形态，输入 OHLCV artifact，输出 JSON |
| `news_filter_tool` | **基于廉价 LLM 的新闻过滤器**：从 OpenAlice 新闻归档取增量，按严重度+持仓相关性评分分级（OQM 不自建 RSS 采集，见「新闻架构」节） |
| `parallel_tool` | 通用并行编排器：并发调用多个已注册工具，输出按 key 聚合的结果 |
| `price_watch_tool` | 价格监控：固定阈值突破 + 异动检测（3σ/3%），输入 ccxt ticker/K线，输出价格事件 |
| `order_watch_tool` | 订单监控：轮询 OpenAlice UTA 挂单/成交，与上次快照 diff，输出订单事件 |
| `event_trigger_tool` | 事件编排器：聚合各监控结果，按事件生命周期冷却，决定是否唤起 openalice_tool |
| `openalice_tool` | HTTP 调 OpenAlice headless API，唤起 Pi agent 决策 |

## 一个前置坑：Docker 网络的认证问题

OpenAlice 的 loopback 免认证只对容器内 127.0.0.1 生效。宿主机经 docker 发布端口访问，来源 IP 是 docker 网桥网关（非 loopback）→ **需要 admin token**（首次启动时打印，`POST /api/auth/login` 换取）。

两种解法，推荐 A：

- **A. token 认证**：把 token 存入 OQM 配置（`QUANT_AGENT_OPENALICE__TOKEN` 环境变量注入，不落明文进 git），`openalice_tool` 带 Authorization 头请求 `http://localhost:47331`。
- B. `docker exec openalice curl localhost:47331/...`（容器内 loopback 免认证）——零 token 但依赖 docker CLI，作为降级方案。

## 新闻架构（2026-07-26 修订：不自建采集，三层设计）

结论：**OQM 不写 RSS 采集器**（那是重复造轮子）。新闻能力分三层：

**L0 原始归档 = OpenAlice 自带新闻模块（唯一采集点）**。RSS collector 持续归档（留存 7 天），agent 用 globRss/grepRss/windowRss 拉取式检索。需要的调整（OpenAlice 侧配置，非代码）：
- `data/config/news.json` 的 `intervalMinutes` 从默认 10 降到 1~2（黑天鹅场景 10 分钟太钝）；
- 确认 feed 列表覆盖加密（CoinDesk/Cointelegraph/The Block）+ 宏观（Fed/Reuters）；
- 已知上限：只有 RSS，无 X/快讯级速度——由 L2 的价格异动通道兜底。

**L1 agent 自维护的叙事记忆（零代码，prompt 契约）**。定时研判与事件唤起共用同一 resumeId/Session，要求 agent 在 workspace 维护 `news/active-narratives.md`（workspace 是 git 仓库，天然版本化）。每条记录一个「活跃叙事」：事件、首见时间、状态（新发/发展中/衰减/已消化）、与持仓的关联、关键事实。每个周期：读文件 → 检索新新闻 → 更新状态迁移。这解决「前几个周期的事件持续影响」——事件不会滑出检索窗口就被遗忘，而是按生命周期衰减。同时 prompt 契约要求 agent：发现价格异动时用 windowRss 回溯 24h/7d 找驱动事件，不只看最近 1 小时（「记得」的第一形态是「能查到」）。

**L2 OQM 侧的过滤与触发（本计划唯二要写的新闻代码）**：
- `news_filter_tool`：**廉价 LLM 过滤器**（gpt-4o-mini / deepseek 级，日成本 < ¥0.1）。从 OpenAlice 归档取增量（走 loopback HTTP 网关，与 headless 同一通道，不自抓 RSS），批量送 LLM 评分，输出 JSON：`severity 0-10 + affected_assets + 一句话理由`。prompt 注入监控标的清单（静态配置），使评估带持仓相关性。动作分三档：高 → 立即唤起 agent；中 → 记入 pending 清单，并入下一次每小时研判上下文；低 → 丢弃。
- **价格异动通道**（独立于新闻的兜底）：15m 收益率超阈值（3σ 或固定 3%）或成交量暴增 → 直接唤起 agent 自己找原因。真正的黑天鹅「市场比新闻先动」，这条线防过滤器漏判。
- 工程要点：按文章哈希去重（每条只评一次，存 watch_state）；**降级链 = LLM 过滤 → 关键词过滤（备胎保留）→ 静默**（禁止 fail-open 直接唤起，防 API 抖动变 agent 风暴）；所有评分+理由落 artifact 存档，供每周回顾调 prompt。

**Awesome-finance-skills 的定位**：不当轮询回路主路（用 LLM 干代码的活，慢且贵）。可选装到 OpenAlice workspace 作为**按需深挖工具**（alphaear-news 覆盖财联社/微博/Polymarket 等 RSS 触及不到的源），agent 发现 RSS 归档解释不了价格异动时自行调用；其 signal-tracker 的「强化/弱化/证伪」生命周期模型已被 L1 吸收。

## 实施步骤

### Phase 0：连通性验证（无代码，约 0.5h）

> **2026-07-26 实测已完成**，关键结论：
> - 容器内 `docker exec` + node fetch 走 loopback 免认证可用；`alice-uta` CLI 在 `/usr/local/bin`，需 `export AQ_WS_ID=<wsId>`。
> - 交易 workspace：`chat-sunny-indigo-field`；UTA 交易账户：`binance-e5b591c8`（trading tier，healthy）；另有 `binance-readonly` 纯数据账户。
> - **`allowAiTrading` 已为 true**：`order place --commit-message ...` + `git push` 直接成交，**无任何人工审批环节**（实测 BUY 6 USDT SUI 永续 → filled 8.2 SUI @ 0.7232 → `position close` → filled，全程无 approve）。
> - U 本位永续 aliceId 形如 `binance-e5b591c8|SUI/USDT:USDT`；下单必须带 `--sub-account-id derivatives`。
> - **实测复现了调研中的已知限制**：order history 里有一笔附带 TP/SL 的单被 loud-refuse（"Attached TP/SL is not verified to reach binance through ccxt"）——Binance 走 ccxt 确实不能附带 TP/SL，决策 prompt 必须要求分腿挂止损。
> - 待办仅剩：确认宿主机→容器端口的 token 认证（docker exec 方案已验证可绕过）、配 PushPlus token。

1. 确认端口发布：`docker port openalice`（应为 47331）。
2. 取 admin token，从宿主机 curl 验证：`POST http://localhost:47331/api/auth/login`。
3. 列出 workspace（`GET /api/workspaces`），选定/新建一个交易 workspace，记录 `workspaceId`。
4. 手动验证唤起链路：`POST /api/workspaces/:id/headless`（body `{"prompt": "用 alice-uta 查询当前账户概况并总结", "wait": true}`），确认 Pi agent 能在 headless 下正常调 alice-uta 读 Binance 仓位。
5. 确认 OpenAlice 侧 `allowAiTrading` 状态：保守起步 = 关（决策变提案，人工 push 需 curl `POST /api/trading/uta/:id/wallet/push`）；要全自动 = 开 + 配好 guards（max-position-size / cooldown / symbol-whitelist）。注意：用户只有 PushPlus 通知渠道，若走人工审批，通知里要附审批 curl 命令或接受必须开 UI。
6. 在 OQM 配置 PushPlus token：`QUANT_AGENT_NOTIFIER__PUSHPLUS__TOKEN`。

### Phase 1：数据工具（indicator + news_filter + parallel 编排器）

**`tools/market_data/indicator_tool.py`**（新）

- 输入：`symbol / market / interval / limit / fast / slow / ...`（或直接读 `$ohlcv.artifact` CSV 路径）。
- 实现：**统一用 `TA-Lib`** 计算 SMA/EMA/MACD/RSI/BOLL/ATR 及蜡烛图形态，不自己造轮子。`pyproject.toml` 加入 `ta-lib`（Python wrapper）作为依赖。注意：TA-Lib 需要底层 C 库 `ta-lib`；开发环境若缺头文件，可直接安装预编译轮 `TA-Lib-Precompiled`，或在 Debian/Ubuntu 先执行 `apt-get install ta-lib-dev`，或改用 conda 安装 `ta-lib`（含 C 库）。运行环境（OQM 宿主机/docker）需在部署文档里明确安装步骤。
- 输出：结构化 JSON（各指标最新值 + TA-Lib 形态标签 + 简要信号倾向），落 artifact。
- 测试：`tests/tools/test_indicator_tool.py`，用固定 CSV 断言指标数值。

**`tools/news/news_filter_tool.py`**（新，替代原 RSS 采集方案）

- 数据源：调 OpenAlice 新闻归档检索（loopback HTTP 网关调 globRss/grepRss，与 openalice_tool 同一通道，复用其 base_url/token/workspace 配置），取 `window_minutes` 增量。
- 过滤：批量送廉价 LLM（OpenAI 兼容接口，模型可配，默认 gpt-4o-mini 或 deepseek-chat；config 新增 `llm: { base_url, api_key, model }`，env `QUANT_AGENT_LLM__*` 注入 key）。prompt 注入 `watch.symbols` 标的清单做相关性评估；要求 JSON 输出 `{severity, affected_assets, reason}`，temperature 0，schema 校验。
- 重试与降级：使用 `tenacity` 重试装饰器（指数退避，3 次重试，超时/5xx/解析失败均触发），仍失败则**不回退关键词**。失败时：记录错误 artifact、向用户 PushPlus 推送一条「新闻过滤器异常降级」告警，并让**价格异动通道**继续独立值守。这样 LLM 通道失效是可观测的，而不是悄悄降级成更差的方案。
- 去重与生命周期：按文章哈希存 `data/watch_state.json`，每条只评一次；事件状态（新发/发展中/衰减/已消化）驱动冷却（见「事件生命周期冷却与 watch_state.json」专节）。
- 输出：`{ scored: [...], high: [...], medium_pending: [...] }`，全部评分落 artifact 供回顾调参。
- 测试：mock LLM 响应 + mock 归档 API。

### Phase 2：openalice_tool + 定时 pipeline

**`tools/agent/openalice_tool.py`**（新）

- 输入：`prompt / wait（默认 true）/ timeout_sec / resume（bool）`。
- 实现：HTTP POST `{base_url}/api/workspaces/{workspace_id}/headless`，body 带 `prompt`、`wait`、`resumeId`；prompt 上限 16000 字符，工具内做截断保护。
- `resumeId` 持久化：首次调用后保存到 `data/openalice_session.json`（简单文件即可，不入 state_store 表），后续调用带上，使每次研判回到同一 Session、上下文连续。
- 配置：`config.yaml` 新增 `openalice: { base_url, workspace_id, token, default_timeout }`，env 覆盖 `QUANT_AGENT_OPENALICE__*`。
- 依赖：httpx 已在 dev 依赖，移到主依赖（或用标准库 urllib，零新依赖）。
- 测试：mock HTTP server。

**`tools/runtime/parallel_tool.py`**（新，通用并行工具，替代原 `market_context_tool`）

- 输入：`calls`（map，key → `{ tool: <name>, inputs: {...} }`）。通过 `ToolRegistry` 查找并并发调用已注册工具，用 `asyncio.gather` 并行执行。输出：`{ <key>: <tool_result> }`。
- 限制：**不允许递归调用自己**（`parallel_tool` 不能出现在 `calls` 中）；任一 child 失败即整体失败（与 pipeline runner 的 fail-stop 一致）。
- 优势：通用的 pipeline 并行能力，runner 仍保持简单顺序语义；未来任何需要并行的场景（如同时查多个标的的指标、多个数据源）都可复用。
- 测试：mock 两个子工具 + 断言并发/失败行为。

**`pipelines/hourly_review.yaml`**（新，cron `3 * * * *`——错开整点避开并发高峰）

```yaml
stages:
  - ohlcv:        ohlcv_tool      # 拉 1h K 线 artifact
  - context:      parallel_tool   # 通用并行：指标计算 ∥ 新闻过滤
      inputs:
        calls:
          indicators:
            tool: indicator_tool
            inputs:
              artifact: "$ohlcv.artifact"
          news_digest:
            tool: news_filter_tool
            inputs:
              window_minutes: 60
  - decide:       openalice_tool  # prompt 模板注入 $context.indicators、$context.news_digest
  - notify:       notify_tool     # body: $decide.summary, channels: [pushplus]
```

decide 的 prompt 模板要点（在 YAML inputs 里拼装）：「以下是最近 1 小时的技术指标、K 线形态与新闻摘要（含 watch 累计的 medium 级待办新闻）。请：1. 读取并更新 workspace 里的 `news/active-narratives.md`（活跃叙事：新发/发展中/衰减/已消化）；2. 若价格有异动，用新闻归档的时间窗查询回溯 24h~7d 找驱动事件，不要只看最近 1 小时；3. 用 alice-uta 查询当前 Binance 账户仓位与挂单；4. 综合研判后给出操作决策并按既定规则执行（止损必须分腿单独挂单，不得附带 TP/SL）；5. 用一段话给出面向用户的总结。」

## 事件生命周期冷却与 watch_state.json

### 为什么不用简单时间冷却

简单时间冷却（"30 分钟内同一类事件不重复触发"）有两个问题：

1. **会漏升级**：如果 10 分钟前刚触发过，但 5 分钟后出现了更高级别的新进展（severity 从 5 跳到 9），时间冷却会把它吞掉；
2. **会机械重复**：30 分钟一过，同一篇旧新闻还会反复触发，因为 RSS 中它仍在窗口内。

生命周期冷却跟踪的是**"故事"本身**，不是时钟。每个事件有自己的状态机：

```
new ──首次触发──► developing ──升级──► (再触发)
 │                    ▲
 │                    │ 有升级
 ▼                    │
fading ◄──2h 静默─────┘
 │
 ▼ 12h 静默
resolved
```

### 状态定义与触发规则

| 状态 | 含义 | 是否触发 |
|---|---|---|
| `new` | 首次出现的事件/文章 | **触发** |
| `developing` | 已触发过，仍在进展中 | 仅当**升级**：severity 涨 ≥2、出现新维度（如新闻+价格异动同时命中）、或冷却期外有实质新信息 |
| `fading` | 2h 无新进展 | 仅当高 severity 新文章将其重新激活 |
| `resolved` | 12h 静默 | 不触发；真正的"新故事"会生成新 event id，不受影响 |

举例（美伊事件）：

- 08:00 「德黑兰传出爆炸声」severity 7 → `new`，触发，进入 `developing`；
- 09:30 「美方确认空袭」severity 9 → `developing` 状态，severity 涨 2 → 升级，再触发；
- 10:00 五篇类似报道 severity 7~8 → `developing`，无升级 → 静默；
- 13:00 无新消息 → 转 `fading`；
- 次日 → `resolved`。

整个过程你被通知 **2 次** 而不是 20 次。

### watch_state.json 结构

```json
{
  "version": 1,
  "articles": {
    "a1b2c3d4": {
      "title": "Explosions heard in Tehran",
      "first_seen": "2026-07-26T08:02:11Z",
      "severity": 7,
      "event_id": "evt_mideast_20260726"
    }
  },
  "events": {
    "evt_mideast_20260726": {
      "type": "news",
      "label": "中东冲突升级",
      "state": "developing",
      "first_triggered_at": "2026-07-26T08:02:15Z",
      "last_triggered_at": "2026-07-26T09:31:04Z",
      "trigger_count": 2,
      "last_severity": 9,
      "cooldown_minutes": 30,
      "related_hashes": ["a1b2c3d4", "e5f6g7h8"]
    },
    "price_SUIUSDT_vol_spike": {
      "type": "price",
      "state": "fading",
      "last_triggered_at": "2026-07-26T06:10:00Z",
      "trigger_count": 2,
      "cooldown_minutes": 30
    }
  },
  "orders_snapshot": {
    "open_order_ids": ["40256528251"],
    "last_check": "2026-07-26T08:00:00Z"
  },
  "pending_medium": [
    { "hash": "x9y8z7", "title": "SEC delays ETF decision", "severity": 5, "reason": "...", "ts": "..." }
  ]
}
```

各字段说明：

- `articles`：已评分文章的哈希 → 归属事件 id（实现去重 + 事件聚合）；
- `events`：活跃事件的状态机记录，是生命周期冷却的核心；
- `orders_snapshot`：订单 diff 的基准快照；
- `pending_medium`：medium 级新闻，等每小时研判消费。

### 全局兜底保险

即使状态机判了触发，还要过一道硬性节流阀：任意两次唤起 agent 之间至少间隔 10 分钟。这是防止代码 bug 导致触发风暴的最后一道闸门。

### Phase 3：事件监控（拆分为四个单一职责工具 + event pipeline）

**`tools/research/price_watch_tool.py`**（新）
- 输入：`symbols`（带 `above`/`below` 阈值）、`volatility_window`。
- 实现：ccxt 拉 ticker/K线，做固定阈值判断 + 15m 收益率 3σ（或固定 3%）异动检测 + 量能暴增判断。输出结构化价格事件：`{ triggered: bool, symbol, event_type, price, change_pct, reason }`。
- 测试：mock ccxt。

**`tools/research/order_watch_tool.py`**（新）
- 输入：`uta_id`（默认 binance-e5b591c8）。
- 实现：调 OpenAlice UTA API 查当前挂单/成交，与 `data/watch_state.json` 里的上次快照 diff，输出订单事件（新挂单、成交、撤单、部分成交）。更新快照。
- 测试：mock UTA API。

**`tools/research/event_trigger_tool.py`**（新，聚合与触发）
- 输入：`$price` / `$news` / `$orders` 各监控结果。
- 实现：应用**事件生命周期冷却**并决定是否触发；内部调用 `openalice_tool` 的唤起逻辑（import 复用），prompt 注入事件载荷。输出 `{ triggered: bool, summary: str }`。
- 内部逻辑（7 步）：
  1. **归一化为候选事件**：price → `price:{symbol}:{event_type}`；news → 高 severity 文章查 `articles` 表归属已有事件，未归属则新建 event id（slug(category+日期)）；orders → `order:{uta}:{orderId}`；
  2. **状态机判定**：无记录 → `new` 立即触发；`developing` → 仅升级才触发（severity 涨 ≥2、出现新维度如新闻+异动同时命中、或冷却期外实质新信息）；`fading` → 仅高 severity 新文章触发；`resolved` → 永久静默（新故事会生成新 event id，不受影响）。全局兜底：任意两次触发最小间隔 10 分钟；
  3. **状态迁移（无论是否触发都执行）**：`new → developing`（首次触发后）；`developing → fading`（2h 无相关新文章/价格联动）；`fading → resolved`（12h 静默）；resolved 记录 7 天后清理。**迁移与判定分离**是关键——否则事件永远停在 developing；
  4. medium 级新闻不进状态机，追加到 `pending_medium`（等 hourly_review 消费）；
  5. 有触发 → 聚合载荷（事件 + severity + 理由 + 价格/订单数据）→ 调 openalice_tool（同一 resume Session）→ 返回 summary；
  6. 无触发 → 返回 `{triggered: false, summary: ""}`；
  7. 无论触发与否，持久化 `watch_state.json`。
- `data/watch_state.json` 结构：`{ articles: {hash → {title, first_seen, severity, event_id}}, events: {event_id → {type, label, state, first/last_triggered_at, trigger_count, last_severity, cooldown_minutes, related_hashes}}, orders_snapshot: {open_order_ids, last_check}, pending_medium: [...] }`。
- 测试：冷却状态机单测（覆盖 new/developing 升级/fading 复活/resolved 静默/全局节流）。

**`pipelines/event_watch.yaml`**（新，cron `*/10 * * * *`）

```yaml
stages:
  - monitor: parallel_tool
      calls:
        price:    { tool: price_watch_tool,   inputs: { symbols: ["SUIUSDT"] } }
        news:     { tool: news_filter_tool,   inputs: { window_minutes: 20 } }
        orders:   { tool: order_watch_tool,   inputs: { uta_id: "binance-e5b591c8" } }
  - trigger: event_trigger_tool
      inputs:
        price:   "$monitor.price"
        news:    "$monitor.news_digest"
        orders:  "$monitor.orders"
  - notify:  notify_tool
      inputs:
        subject: "OpenAlice 事件触发"
        body:    "$trigger.summary"
        channels: [pushplus]
```

`notify_tool` 需要支持空 body 跳过（`$trigger.triggered == false` 时 summary 为空）——一行短路逻辑。

### Phase 4：收尾

- `config.yaml` + `.env.example` 补全：`openalice.*`、`llm.*`（廉价过滤模型）、`watch.*`、PushPlus token 样例。
- **OpenAlice 侧配置（非代码）**：`data/config/news.json` 的 `intervalMinutes` 调为 1~2 并确认 feed 列表；可选——把 Awesome-finance-skills 的 `alphaear-news` 等技能装进交易 workspace（`.claude/skills/`），作为 agent 按需深挖工具（覆盖财联社/微博/Polymarket 等 RSS 之外的源）。
- `AGENTS.md` / `AGENT_GUIDE` 更新：新工具清单与两个 pipeline 的说明。
- `oqm-tool` skill（`skills/core/`）补新工具的用法示例。
- 端到端验证：daemon 常驻 → 手动 `quantmaster-daemon --run hourly_review` 全链路跑一次（确认 agent 生成/更新了 `active-narratives.md`）→ 人为构造一次 watch 触发（调低价格异动阈值）验证事件链路 → 确认 PushPlus 收到通知 → 检查评分 artifact 抽查 LLM 过滤质量。

## 不在本期范围

- OpenAlice 源码改动（零改动，全部走其公开 HTTP API）。
- OQM 的 `account/`、`execution/`、`risk/` 工具（仓位查询与执行由 OpenAlice 侧承担，避免双写 Binance 凭证与双套风控）。
- pipeline runner 的并行/条件分支扩展（当前用工具内短路规避）。
- Vibe-Trading 接入实时链路（仅离线回测用途）。

## 风险与注意事项

- **headless 并发上限 8**：watch 事件生命周期冷却 + 定时任务错开整点几分钟（如 cron `3 * * * *`）。
- **OpenAlice UTA 的已知短板**（见调研文档）：Binance 非官方验收最充分的 venue；CCXT 不支持附带 TP/SL（已实盘复现 loud-refuse）——决策 prompt 中已明确要求 agent 分腿挂止损。
- **TA-Lib 原生依赖**：`indicator_tool` 使用 TA-Lib，部署/CI 需预装底层 C 库或预编译轮；开发文档和 `.env.example`/README 要给出安装命令（apt/conda/TA-Lib-Precompiled）。
- **LLM 过滤器失败模式**：`tenacity` 指数退避 3 次重试后仍失败则不回退关键词，改为 PushPlus 告警「新闻过滤器异常降级」；价格异动通道作为过滤漏判的最终兜底，两者都不可省略。
- **prompt 16000 字符上限**：新闻摘要和 pending 清单在 context 工具内做条数/长度截断。
- **resumeId 失效**：Session 被清理后带旧 resumeId 会失败，openalice_tool 需在 404/400 时自动重建 Session（重建后 `active-narratives.md` 是记忆连续性的保障，文件在记忆就在）。
- **订单状态监控频率**：`*/10` cron 对成交感知是分钟级延迟，可接受；更快需缩短到 `*/5`，注意 token 消耗。
- **LLM 过滤成本**：gpt-4o-mini 级模型日成本 < ¥0.1，但需在 config 中配 `llm.api_key`（与 OpenAlice 的 agent key 相互独立）。

## 工作量估算

| 项 | 估时 |
|---|---|
| Phase 0 连通性验证（已完成） | 0.5h |
| indicator_tool + news_filter_tool + parallel_tool + 测试 | 4-6h |
| openalice_tool + hourly pipeline + 测试 | 2-3h |
| price_watch_tool + order_watch_tool + event_trigger_tool + event pipeline + 测试 | 3-4h |
| Phase 4 收尾（含 OpenAlice 侧新闻配置）+ 端到端 | 1-2h |
