# Agentmanage Prompt Template

将下面内容作为 agentmanage 的单次执行 prompt，按需修改配置。未填写的配置使用 `SKILL.md` 中的默认值。

在 agentmanage 中使用同一 prompt 配置三个 Asia/Shanghai 调度：09:20（盘前）、11:35（午间）、14:45（尾盘）。对应 cron 可写为 `20 9 * * *`、`35 11 * * *`、`45 14 * * *`；每天触发后由 Skill 先检查交易日，非交易日直接跳过。Skill 本身不创建调度。

```yaml
task: 使用 cn-portfolio-advisor Skill 执行一次持仓复盘并给出交易建议
session: auto
timezone: Asia/Shanghai
state_file: .agent-state/cn-portfolio-advisor/state.json

# 首次使用前必须确认真实持仓。每次持仓变动，更新 holdings 并将版本号加 1；
# 如果只修改其他配置，不要增加版本号。明确当前空仓时也可确认，holdings 保持空列表。
portfolio_revision: 1
portfolio_confirmed: false
cash_cny: null
risk_profile: balanced
max_single_position_pct: 20

# 示例字段，取消注释并替换为真实持仓；不要把示例当成实际持仓。
# holdings:
#   - symbol: 600519.SH
#     market: a_share
#     name: 贵州茅台
#     news_symbol: "600519"
#     news_keywords: ["贵州茅台", "白酒", "白酒行业政策"]
#     quantity: 100
#     cost_price: 1500.00
#     max_position_pct: 20
#     notes: 中长期持有，未经确认不建议频繁交易
# 基金不填 news_symbol，但必须把基金名称、跟踪指数和相关行业填入 news_keywords。
holdings: []

benchmark_symbol: 000300.SH
bar_limit: 120
news_sources: cls,em,sina,ths,futu
news_limit: 100
stock_news_limit: 50
initial_news_lookback_hours: 24
news_overlap_minutes: 15

# qm-cli 当前没有交易日历服务。必须自行核对并维护当年休市日期；
# 日历未覆盖当前日期时，工作日会暂停分析并提醒更新。
# 示例格式：non_trading_dates: ["2026-01-01", "2026-02-16"]
non_trading_dates: []
trading_dates_override: []
calendar_confirmed_through: null

# 用户固定关注的事件可在这里初始化；运行中发现的重大可观察事件会写入状态文件。
# 示例格式：
# watch_events:
#   - id: example-penalty-decision
#     title: 某上市公司证监会处罚落地
#     symbols: ["600000.SH"]
#     keywords: ["公司名称", "行政处罚", "处罚决定"]
#     trigger: 证监会或公司正式披露处罚决定
#     hypothesis: 若处罚不重于市场预期，可能出现利空出尽；仍需验证
#     pinned: true
#     expires_at: "2026-12-31T23:59:59+08:00"
watch_events: []

instructions: |-
  只提供交易建议和通知，不自动下单。
  持仓以用户确认的快照为准；实际买卖后由用户更新持仓并递增 portfolio_revision。
  每次只分析上次成功运行至今的重要增量新闻，披露来源时间、覆盖缺口和未证实消息。
  只跟踪有明确催化或风险节点的事件，忽略鸡毛蒜皮的信息；固定关注项不得擅自删除。
  发现黑天鹅或重大持仓风险时立即单独通知；三次调度之间不承诺持续监控。
  在此补充个人偏好、禁止事项、目标持有期或其他特殊指令。
```
