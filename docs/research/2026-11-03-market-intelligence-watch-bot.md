# Market Intelligence Watch Bot — Vision, Difficulties, Tooling

> Date: 2026-11-03
> Status: research note (not an implementation spec)
> Scope: design exploration for a periodic market-intelligence bot on top of OpenQuantMaster

## 1. Vision

A bot that, on a fixed cadence, watches a configurable watchlist and answers:

- Did anything **materially positive or negative** happen for the watched assets?
- Is this **new**, or something we already saw?
- Does it **connect** to other recent events or to past decisions?
- What could it mean for the **short term (days)** and the **long term (months)**?

Behavior contract:

- **Quiet by default.** No material change → no notification, only a log line.
- **Explain, not just alert.** When it does speak, it gives reasoning, evidence links, competing hypotheses, and confidence.
- **Hand off.** Findings can be passed to other agents (research, risk, portfolio) as structured records.
- **No autonomous execution.** Trading decisions remain human-approved.

Example watchlist:

| Asset / topic | Kind | Notes |
|---|---|---|
| Crypto market trend | macro | overall regime, funding, OI |
| SUI/USDT structure | crypto | 1h / 4h / 24h patterns |
| 600015 (Huaxia Bank) | a_share | price, volume, filings |
| 000001.SH (SSE Composite) | index | market regime |
| Northbound flows | flow | daily net buy / balance |
| "National team" activity | flow | ETF share changes, large broad ETFs |
| Selected ETFs | etf | share/volume changes |

## 2. Recommended Form

**Deterministic pipeline + cron + on-demand LLM + push channel.**
The LLM is an on-demand analyst, **not** a resident agent.

| Candidate form | Verdict | Reason |
|---|---|---|
| CLI pipeline + cron | **Primary** | testable, replayable, idempotent, cheap |
| Resident collector (websocket) | optional, data only | CCXT ws fits here; no judgment logic inside |
| Resident LLM agent bot | reject | cost, latency, non-reproducibility |
| Autonomous trading | later / never default | keep human approval |

Three rules that decide whether this survives its first month:

1. **Indicators and threshold checks live in code; the LLM only explains, correlates, and narrates.**
2. **The LLM never invents numbers.** Every figure comes from the collected structured facts.
3. **Every conclusion traces back to a source URL / provider call + timestamp.**

## 3. Proposed Architecture

```text
cron (existing APScheduler daemon, or systemd timer)
  │
  ├─ collect  (deterministic, no LLM)
  │    ├─ prices: ohlcv_tool (ccxt / tushare / akshare / yfinance)
  │    ├─ indicators: indicator_tool + ta library
  │    ├─ events: news tools, filings, Polymarket, watchlist sources
  │    └─ persist raw observations (StateStore / SQLite)
  │
  ├─ gate     (deterministic — silence happens here)
  │    ├─ dedup: URL/event fingerprint + semantic similarity
  │    ├─ triggers: breakout, volume spike, flow anomaly, filing hit
  │    └─ nothing fired → write log, exit (zero LLM, zero push)
  │
  ├─ analyze  (LLM, only when fired)
  │    ├─ inject structured facts + events + relevant memory
  │    ├─ attribution, short/long view, ≥2 competing hypotheses
  │    └─ structured JSON: stance, confidence, evidence ids, falsifier
  │
  ├─ decide   (deterministic)
  │    ├─ importance / confidence / novelty filter → disturb user?
  │    ├─ notify_tool (PushPlus today; Bark / ntfy / Telegram)
  │    └─ handoff: JSONL queue / MCP for other agents
  │
  └─ settle   (daily)
       └─ resolve past predictions vs realized price → Brier, hit rate
```

### Watchlist sketch

```yaml
schedule: "7 * * * *"          # hourly, minute 7 — avoid the top-of-hour rush
timezone: Asia/Shanghai
quiet:
  max_push_per_day: 3
  min_importance: 0.6
assets:
  - {id: "SUIUSDT", kind: crypto, source: ccxt, timeframes: [1h, 4h, 24h]}
  - {id: "600015.SS", kind: a_share, source: akshare}
  - {id: "000001.SS", kind: index, source: akshare}
  - {id: "northbound", kind: flow, source: akshare}
news:
  recall_window: 7d
  source_tiers: {primary: 1, media: 2, social: 3}
memory:
  backend: sqlite              # upgrade path: graph memory
  dedup: {exact: url_hash, semantic: "cosine>0.92"}
handoff:
  targets: [research-agent, risk-agent]
  format: jsonl
```

### Minimal data model

```sql
CREATE TABLE events (
  id TEXT PRIMARY KEY,          -- content fingerprint
  kind TEXT,                    -- news / filing / flow / price
  asset TEXT,
  occurred_at TEXT,             -- when it actually happened
  ingested_at TEXT,             -- when we saw it
  source_url TEXT,
  source_tier INTEGER,          -- 1 primary, 2 media, 3 social
  title TEXT, summary TEXT,
  payload JSON,
  notified_at TEXT              -- NULL = never pushed
);
CREATE TABLE signals (          -- every gate evaluation, fired or not
  id TEXT PRIMARY KEY, run_at TEXT, asset TEXT,
  rule TEXT, trigger_value REAL, threshold REAL,
  fired INTEGER, acted INTEGER
);
CREATE TABLE decisions (
  id TEXT PRIMARY KEY, run_at TEXT, asset TEXT, horizon TEXT,
  stance TEXT, confidence REAL, rationale TEXT,
  evidence JSON, counter_hypothesis TEXT, falsifier TEXT,
  settled_at TEXT, outcome REAL
);
```

## 4. Key Difficulties

Ordered by how likely each is to break the system in practice.

### 4.1 Cost and noise control

An hourly LLM pass burns tokens even when it says nothing. Threshold evaluation must be pure code, and the LLM must only run when something fires. Add a daily push cap and per-asset cooldowns.

### 4.2 Deduplication is harder than it looks

- The same story appears as a press release, ten media rewrites, and a dozen social posts.
- URL fingerprints alone are insufficient; need event-level clustering (entity + time window + semantic similarity).
- Re-notifying a resolved item destroys trust faster than missing one.

### 4.3 Time semantics

- `occurred_at` ≠ `ingested_at`: a 03:00 fetch of a 08:00 event corrupts the timeline if conflated.
- Never compute patterns on an **unclosed candle** — 1h/4h signals must use closed bars only.
- Timezones and market sessions differ per asset class; crypto is 24/7, A-shares are not.

### 4.4 Data coverage and caliber drift

- Northbound flow definitions changed in 2024; interfaces differ between "net buy today" and "quota balance". Verify per-interface semantics before setting thresholds.
- Free providers rate-limit and silently change schemas. A failed source must be recorded as **unknown coverage**, never as "no news".

### 4.5 Hallucinated numbers and broken provenance

LLMs freely invent prices and percentages. Mitigation: inject only structured facts, require every figure in the output to appear in the fact table, and validate programmatically before sending.

### 4.6 Correlation is not causation

"Northbound inflow + stock up + policy rumor" is not insider trading. Outputs must be framed as **hypotheses with falsifiers**, with at least two competing explanations. This is the central epistemic risk of the whole design.

### 4.7 Prompt injection from collected content

News pages, blog posts, and PDFs are **data, never instructions**. Collection should run with minimal tool privileges; analysis should receive sanitized text only.

### 4.8 Memory model choice

Vector-only recall finds "similar text", not "related events". The useful structure is entity–event–time–evidence links. Starting with SQLite + explicit relations is fine; a graph memory backend is a later upgrade, not a prerequisite.

### 4.9 Evaluation and calibration

Without settlement, a year of confident predictions tells you nothing. Every recorded decision needs a resolution rule and an outcome; track Brier score and hit rate per asset and per rule.

### 4.10 Multi-agent handoff contract

Handoffs must be structured records (asset, horizon, stance, evidence ids, confidence, falsifier), not prose. Otherwise downstream agents inherit unverifiable narrative.

### 4.11 Notification fatigue

Group by asset, batch non-urgent items into a daily digest, reserve immediate push for high-materiality events only.

## 5. Related Tools and Projects

All entries below were checked against their official repositories on 2026-11-03.

### 5.1 Data sources

| Need | Project | Notes |
|---|---|---|
| Crypto OHLCV, order book, trades | [CCXT](https://github.com/ccxt/ccxt) | 100+ exchanges; official MCP server `claude mcp add ccxt -- npx -y ccxt-mcp`; CLI; agent skill `npx skills add ccxt/ccxt`. Public market data needs no key. Already used by `ohlcv_tool`. |
| A-shares, indices, northbound, ETFs | [AKShare](https://github.com/akfamily/akshare) + AKTools MCP | AKTools exposes only three generic tools (`search_interfaces`, `describe_interface`, `get_data`) so agents can call any AKShare interface in natural language. `claude mcp add aktools -- uvx --from aktools aktools-mcp`. |
| A-share alternative | [TuShare](https://github.com/waditu/tushare) | Pro token required; already supported by `ohlcv_tool`. |
| Multi-market unified data | [OpenBB](https://github.com/OpenBB-finance/OpenBB) | Data platform with MCP server and REST API. |
| US / HK equities | yfinance | Already supported by `ohlcv_tool`. |
| A-share filings | [use_cninfo](https://github.com/rollysys/use_cninfo) | CNINFO fetch, PDF → Markdown, local cache, category filters. |
| Chinese social / hot search | [last30days-cn](https://github.com/Jesseovo/last30days-skill-cn) | Weibo, Xiaohongshu, Bilibili, Zhihu, Douyin, WeChat, Baidu, Toutiao; daily hot-list aggregation. |
| Broad recent-web research | [last30days](https://github.com/mvanhorn/last30days-skill) | Reddit, X, YouTube, HN, Polymarket, GitHub; `--store` SQLite, watchlist scheduling, briefing. |
| Prediction-market odds | [Polymarket agent-skills](https://github.com/Polymarket/agent-skills) | Market-implied probabilities as a secondary signal. |

### 5.2 Indicators and analysis

| Project | Reuse |
|---|---|
| [ta](https://github.com/bukosabino/ta) | 43 indicators (MACD, RSI, ADX, Bollinger, ATR, Stoch…), pure pandas. Complements `indicator_tool`. |
| [TradingAgents](https://github.com/TauricResearch/TradingAgents) | Closest architectural reference: parallel analysts → bull/bear debate → trader → risk → portfolio manager. Cron-friendly flags, memory log that **settles past decisions and writes reflections**, grid backtesting, A-share `.SS/.SZ` and crypto support, Moonshot/Kimi provider. |
| [ai-hedge-fund](https://github.com/virattt/ai-hedge-fund) | Mandate files, hash-chained session ledger, **approval step before execution**, paper-trading mode. |
| [structured-analytic-skills](https://github.com/radarist/structured-analytic-skills) | ACH competing hypotheses, source reliability grading, horizon scanning, indicators validation, Brier calibration. |
| [superforecasting-skill](https://github.com/deusyu/superforecasting-skill) | Resolvable forecasts, append-only ledger, evidence-based probability updates, Brier scoring. |

### 5.3 Memory

| Project | Notes |
|---|---|
| MCP reference [Memory](https://github.com/modelcontextprotocol/servers) + [Sequential Thinking](https://github.com/modelcontextprotocol/servers) | Knowledge-graph memory and structured reasoning as MCP servers. |
| [Mnemon](https://github.com/mnemon-dev/mnemon) | Temporal / entity / causal / semantic graphs; `remember` / `link` / `recall`; single binary. |
| [MuninnDB](https://github.com/scrypster/muninndb) | Hebbian co-activation links, decay, semantic triggers; pairs with OSINT workflows. |
| [Graphiti](https://github.com/getzep/graphiti) | Bi-temporal graph, provenance to raw episodes, fact invalidation instead of deletion. Best fit when validity windows matter. |

### 5.4 Execution (later phases only)

- [freqtrade](https://github.com/freqtrade/freqtrade) — crypto bot, dry-run, backtesting, hyperopt, WebUI, Telegram control.
- [NautilusTrader](https://github.com/nautechsystems/nautilus_trader) — Rust event-driven core, backtest/live identical strategy code.
- [Hummingbot](https://github.com/hummingbot/hummingbot) + **Condor** — AI harness separating LLM decision-making from deterministic execution, controlled via Telegram/web.

### 5.5 Notification

- **PushPlus** — already configured in `notifier` (`notify_tool`).
- [Bark](https://github.com/Finb/Bark) — iOS push, grouping, time-sensitive and critical alerts, tap-through URL. Best fit for per-asset message grouping.
- [ntfy](https://github.com/binwiederhier/ntfy) — self-hostable HTTP pub-sub.
- Telegram Bot / Feishu / WeCom webhooks.

### 5.6 Scheduling

- **Existing APScheduler daemon** in this repo (`trigger.type: cron` in pipeline YAML) — sufficient for M0–M2.
- `systemd timer` for host-level supervision and restart.
- Kimi Code `CronCreate` for ad-hoc or session-scoped jobs.

## 6. Fit With the Current Repository

Already available:

- `ohlcv_tool` — ccxt / yfinance / tushare / akshare market data
- `indicator_tool` — technical indicators
- `notify_tool` — PushPlus notifications
- cron pipeline triggers, `StateStore`, dry-run execution defaults

Empty packages that this vision would fill:

- `tools/news/` — event ingestion and dedup
- `tools/memory/` — event/decision store and recall
- `tools/equities_data/` — A-share fundamentals, flows, filings
- `tools/research/` — LLM attribution and hypothesis generation
- `tools/risk/` — materiality and confidence gating
- `tools/approval/` — human approval for any downstream action

**Implication:** this is an extension of the existing pipeline runtime, not a new project. The first milestone needs no LLM and no new infrastructure beyond one or two tools plus a pipeline manifest.

## 7. Phased Roadmap

| Phase | Goal | LLM? | Deliverable |
|---|---|---|---|
| **M0** | Deterministic monitoring: collect + thresholds + quiet push | no | `watchlist_gate` pipeline, event/signal tables, PushPlus/Bark alerts |
| **M1** | On-trigger attribution with evidence validation | yes, on trigger | `research` tool, structured fact injection, evidence-id check |
| **M2** | Event relations and competing hypotheses; agent handoff | yes | relation store, ACH matrix, JSONL handoff queue |
| **M3** | Prediction calibration | yes | daily settlement, Brier/hit-rate reports per asset and rule |
| **M4** (optional) | Semi-automatic execution: signal → suggestion → human confirm → dry-run | limited | integration with freqtrade / Nautilus / Hummingbot Condor |

**M0 is the correct starting point.** A watchlist, thresholds, and quiet push deliver a trustworthy base without any model cost. Correlation and inference belong after the base has run quietly and correctly for a while.

## 8. Open Questions

1. Notification channel: Bark (iOS) vs PushPlus vs Telegram vs Feishu?
2. Is anything beyond dry-run ever permitted? Recommendation: stay at M3 until measured hit rate justifies otherwise.
3. Host: is this machine 24/7? Long-running reliability favors daemon + systemd + container over an interactive session.
4. Initial asset scope: start with a single asset (e.g. SUI/USDT) to tune thresholds before expanding the list.
5. Which rules earn an immediate push versus a daily-digest slot?
