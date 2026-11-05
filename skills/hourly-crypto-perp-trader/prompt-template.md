# Agentmanage Prompt Template

将下面内容作为 agentmanage 的单次执行 prompt，按需修改配置。未填写的配置使用 `SKILL.md` 中的默认值。

```yaml
task: 使用 hourly-crypto-perp-trader Skill 执行一次完整交易周期

symbol: BTCUSDT
perp_symbol: BTC/USDT:USDT

# K 线与技术指标周期。调用 qm-cli 时，ohlcv 和 indicator 都使用这个 interval。
# 它不是调度周期；任务何时运行由 agentmanage 决定。
interval: 1h
bar_limit: 200
indicators: sma,ema,macd,rsi,boll,atr
patterns: ALL

news_sources: cls,em,sina,ths,futu
news_limit: 50

# 每个标的/策略使用独立状态文件；更换 symbol 时也应更换路径。
state_file: .agent-state/hourly-crypto-perp-trader/BTCUSDT.json

# 给 agent 的初始本金/基准资金，不是账户真实余额，也不是固定上限。
# 有效额度 = max(0, 初始本金 + 累计已实现盈亏)。盈利可继续交易，亏损后只能使用剩余额度。
allocated_balance_usdt: 20

# false：只 dry-run；true：明确授权实盘，写操作直接使用 --live，不先 dry-run。
live: false
max_leverage: 1
max_new_notional_pct: 5
max_risk_pct: 1
allow_long: true
allow_short: true
autonomous: true

instructions: |-
  无额外指示时，根据行情、技术指标、全部 K 线形态、新闻、当前仓位和挂单自主判断。
  在状态文件中持续记录累计已实现盈亏，并据此更新有效额度；不要把未实现盈亏计入可用资金。
  默认不要查询 balance；仅在状态文件缺失/不清楚，或余额不足等异常需要同步时查询。
  仓位/订单调整或报错时通知用户。遵守 Skill 的其他风控和状态文件要求。
```
