# OpenAlice Inbox 与 BTCUSDT 小时级自动化交易工作流调研

> 来源：与 Kimi Code CLI 的对话总结
> 日期：2026-07-25
> 项目：OpenAlice（ sibling repo `../OpenAlice` ）
> 主题：Inbox 机制、定时 Issue、技术分析、新闻分析、自动交易（含 TP/SL）及安全审批流

---

## 1. OpenAlice 的 Inbox 是什么

Inbox 是 OpenAlice 里 **Agent 向用户交付工作成果的消息/报告收件箱**。

- 每条 Inbox 记录都来自一个 Workspace，是 Workspace 向用户推送的一次“报告”。
- 记录包含：
  - `docs`：指向 Workspace 内文件的相对路径（实时渲染，不做快照）。
  - `comments`：Agent 写的 markdown 消息。
  - `origin`：服务器自动 stamp 的来源信息（runId / issueId / sessionId / agent），Agent 不可伪造。
- 数据存储：
  - 条目：`~/.openalice/data/inbox/entries.jsonl`（只追加 JSONL）。
  - 已读状态：`data/inbox/read-state.json`（与历史分离）。
- 生产写入路径：`inbox_push` 工具（workspace-scoped MCP/CLI 工具）。
- 读取路径：
  - UI 每 20 秒轮询 `/api/inbox/history`。
  - Agent 用 `inbox_read` 回看，可加 `--self` 只看当前 Workspace。

一句话：**Inbox 是 Agent 交作业的投递面，把分散的输出收敛成可追踪、可阅读、可归档的报告流。**

---

## 2. 若要求“每小时看 BTCUSDT、做技术与新闻分析、做决策、自动设止盈止损”，OpenAlice 会怎么做

### 2.1 整体流程

```text
Workspace(如 btc-hourly-trader)
  └─ .alice/issues/btcusdt-hourly.md   ← 自描述 Issue（含 when: every 1h）
       └─ ScheduleScanner 每小时触发
            └─ headless Agent run
                 ├─ 拉行情、算指标
                 ├─ 搜新闻
                 ├─ 评估持仓、生成信号
                 ├─ placeOrder stage 订单（可带 TP/SL）
                 ├─ tradingCommit 提交
                 └─ inbox_push 报告到 Inbox
```

### 2.2 关键安全边界：Trading as Git

- `placeOrder` 只是 **stage**（写入 staged operations）。
- `tradingCommit` 类似 `git commit`，生成一条交易决策记录。
- `tradingPush` 是最终执行步骤，但 **默认被挡住**：
  - 默认 `allowAiTrading = false`。
  - 此时 `tradingPush` 返回提示：需要用户在 Web UI 的 Trading as Git 页面审批。
  - 只有开启 **Settings → Agent Permissions → Allow AI to push trades** 后，Agent 才能直接推送订单到交易所。

### 2.3 止盈止损（TP/SL）

`placeOrder` 的 schema 原生支持 bracket 腿：

```json
{
  "aliceId": "binance-paper|BTCUSDT",
  "action": "BUY",
  "orderType": "MKT",
  "totalQuantity": "0.001",
  "takeProfit": { "price": "70000" },
  "stopLoss": { "price": "62000" }
}
```

---

## 3. 相关 SKILL

| SKILL | 路径 | 用途 |
|---|---|---|
| self-scheduling | `default/skills/self-scheduling/SKILL.md` | Issue 与定时调度 |
| alice-analysis | `default/skills/alice-analysis/SKILL.md` | 技术分析与 Quant Calculator |
| alice-uta | `default/skills/alice-uta/SKILL.md` | 交易执行与 Trading as Git |
| alice-workspace | `default/skills/alice-workspace/SKILL.md` | Inbox、Issue 协作、provenance |
| alice | `default/skills/alice/SKILL.md` | 通用研究、symbol 搜索、RSS |
| traderhub | `default/skills/traderhub/SKILL.md` | 低频市场数据、宏观、板块 |

---

## 4. 相关 Agent Tools（注册名）

### 4.1 数据与分析

- `marketSearchForResearch` — 跨资产 symbol 搜索
- `calculateIndicator` — 简单指标（uppercase formula）
- `calculateQuant`（通过 `alice analysis quant`）— 推荐：barId-keyed 脚本
- `globRss` / `grepRss` / `windowRss` / `readRss` — RSS 新闻归档

### 4.2 交易执行

- `listUTAs`、`searchContracts`、`getContractDetails`、`getQuote`
- `getPortfolio`、`getOrders`
- `placeOrder`（支持 `takeProfit` / `stopLoss`）
- `modifyOrder`、`cancelOrder`、`closePosition`
- `tradingCommit`、`tradingPush`、`tradingReject`、`tradingSync`
- `tradingStatus`、`tradingLog`、`tradingShow`

### 4.3 工作流与交付

- `issue_create`、`issue_update`、`issue_list`、`issue_comment`
- `inbox_push`、`inbox_read`
- `workspace_path`、`workspace_list` 等

---

## 5. 关键 CLI 命令示例

```bash
# 技术分析
alice analysis search-bars --query BTCUSDT
alice analysis quant --script $'h1 = bars("binance-readonly|BTC/USDT", "1h", count=200)\n{ "rsi": rsi(h1.close,14), "atr": atr(h1.high,h1.low,h1.close,14), "sma20": sma(h1.close,20), "price": h1.close[-1] }'

# 新闻
alice rss grep --pattern "BTC|Bitcoin|比特币" --lookback 1h

# 交易账户与持仓
alice-uta account list
alice-uta account portfolio --source binance-paper
alice-uta order list --source binance-paper

# 下单（stage + commit）
alice-uta order place --source binance-paper --symbol BTCUSDT --action BUY --orderType MKT \
  --totalQuantity "0.001" --take-profit-price "70000" --stop-loss-price "62000" \
  --commit-message "Hourly BTC momentum entry"

# Inbox 交付
alice-workspace inbox push --doc signals/btcusdt-hourly.md --comments "BTCUSDT 小时分析完成，已 stage 订单待审批。"

# Issue 管理
alice-workspace issue create --title "BTCUSDT 每小时分析与交易" \
  --when '{"kind":"every","every":"1h"}' --assignee @workspace --agent claude \
  --what "..."
```

---

## 6. Issue Prompt 模板

```markdown
---
title: BTCUSDT 每小时分析与自动交易
status: todo
priority: high
assignee: "@workspace"
when: { kind: every, every: "1h" }
agent: claude
---

每小时执行一次：

1. 数据
   - 用 `alice analysis search-bars --query BTCUSDT` 找到可用的 broker barId。
   - 拉取 1h 和 4h K-line（至少 200 根），计算 RSI(14)、MACD、ATR(14)、SMA(20/50)。

2. 新闻
   - `alice rss grep --pattern "BTC|Bitcoin|比特币" --lookback 1h` 搜索最近 1 小时相关新闻。
   - 如为空，注明“订阅源中无新内容”。

3. 决策逻辑
   - 仅当同时满足时才考虑开仓：
     a. 1h RSI 在 30–70 之间且与趋势同向；
     b. 价格位于 SMA(20) 同侧；
     c. ATR(14) 显示波动率足够；
     d. 无重大利空新闻。
   - 若已有 BTCUSDT 持仓，评估是否需加仓/减仓/平仓/调 TP/SL。

4. 行动
   - 若信号成立：
     - `alice-uta account portfolio` 确认账户状态；
     - `alice-uta order place` stage 一笔市价或限价单；
     - 附加 `takeProfit` 和 `stopLoss`；
     - `tradingCommit` 提交并写明交易理由；
     - **默认不要直接 tradingPush**，把订单信息和分析写入报告。
   - 若信号不成立或条件未满足，只写状态报告。

5. 交付
   - 把分析写入 `signals/btcusdt-hourly.md`。
   - 调用 `alice-workspace inbox push --doc signals/btcusdt-hourly.md --comments "..."`。
```

---

## 7. 要点总结

- Inbox 是 OpenAlice 的**报告投递面**，不是聊天历史。
- 定时工作通过 **Issue + `when` frontmatter** 实现，Scanner 触发 headless Agent run。
- 交易执行遵循 **Trading as Git**：stage → commit → push（需审批）。
- `placeOrder` 原生支持 **takeProfit / stopLoss**。
- 默认 **AI 不能直接 push 订单到交易所**，必须用户 Web UI 批准；开启 `Allow AI to push trades` 后才可自动执行。
- 所有结果应通过 `inbox_push` 交付给用户。
