---
name: hourly-crypto-perp-trader
description: 通过 qm-cli 监控并交易 Binance USDT-M 永续合约。默认监控 BTCUSDT，获取行情、全部 K 线形态、技术指标和 Crypto 新闻，结合本地状态文件检查 agent 额度、仓位与挂单，在用户约束或保守默认规则下自主决策，支持 dry-run 和显式授权的实盘交易，并在仓位/订单调整或报错时通知用户。适用于加密交易、BTCUSDT 监控、永续合约自动交易。
---

# Crypto Perp Trader

每次调用完成一次“读取本地状态 → 数据快照 → 综合判断 → 风控检查 → dry-run / 实盘执行 → 复查、更新状态与通知”的交易周期。默认标的为 `BTCUSDT`，对应 Binance USDT-M 永续合约 `BTC/USDT:USDT`。

调度由 agentmanage 负责；本 Skill 不创建或管理调度任务。配置中的 `interval` 只表示传给行情和指标命令的 K 线周期，不是调度周期。

配置模板见 [prompt-template.md](prompt-template.md)。

## 硬性要求

- 所有行情、指标、新闻、账户、交易和通知操作都必须调用 `qm-cli`；不要直接调用交易所 SDK、HTTP API 或编写脚本绕过它。
- 假设 `qm-cli` 已在 PATH 中，直接运行 `qm-cli ...`。不要传 `--config`。
- **不要阅读、搜索或翻查 qm-cli / OpenQuantMaster 源码来了解用法。** 只使用本 Skill 的示例，以及 `qm-cli help`、`qm-cli list`、`qm-cli run SERVICE --help`。
- 不要把 API Key、Secret、通知 Token、配置秘密或环境变量内容写入状态文件、日志、通知和回复。
- 默认只做 dry-run。只有用户明确说“开启实盘”“允许真实下单”或同等意思，并在 prompt 中设置 `live: true`，才可使用 `--live`。运行、分析、监控、模拟交易等措辞不等于实盘授权。
- 用户未明确开启实盘时，绝不能因为信号很强、用户给了杠杆上限或已经配置交易所凭据而推断可以实盘。
- 实盘模式下可以自主判断和下单，不必逐笔询问，但不得突破用户给出的标的、方向、杠杆、agent 额度、仓位、风险或订单类型限制。
- **实盘写操作直接使用 `--live`，无需先 dry-run。** dry-run 模式只预览，不提交。不要批量盲下订单，不要在失败后自动重复提交同一实盘订单。
- 必须使用一个本地状态文件记录 agent 额度、当前仓位、挂单和最近订单。状态文件读写使用文件工具，不通过 qm-cli。
- 默认不要查询 `balance`。只有状态文件缺失/损坏/关键字段不清楚，或下单出现余额不足、账户状态不一致等异常时，才查询并同步余额。
- 行情、指标、仓位或挂单等关键数据失败/过期/不完整时，本周期停止新增或扩大仓位；不要靠猜测补数据。不要因报错而盲目撤销已有保护性订单。
- 通知也必须通过 `qm-cli run notification`。仓位或订单调整、任何服务报错时都要尝试通知；无调整且无错误时不发送常规通知，避免反复刷屏。

## 配置

从用户最新指令和 agentmanage 提供的 prompt 中读取配置。未提供的值使用下表默认值。可复制 `prompt-template.md` 修改。

| 配置 | 默认值 | 说明 |
|---|---|---|
| `symbol` | `BTCUSDT` | 行情与指标代码 |
| `perp_symbol` | `BTC/USDT:USDT` | Binance USDT-M 永续合约代码；特殊代码让用户明确给出 |
| `interval` | `1h` | 原样传给 `ohlcv` 和 `indicator` 的 K 线周期，不是调度周期 |
| `bar_limit` | `200` | K 线数量，须足以覆盖最长指标和形态回看期 |
| `indicators` | `sma,ema,macd,rsi,boll,atr` | 逗号分隔 |
| `patterns` | `ALL` | 默认计算全部 TA-Lib K 线形态；也可给逗号分隔列表，设为空可跳过 |
| `news_sources` | `cls,em,sina,ths,futu` | 新闻来源 |
| `news_limit` | `50` | 过滤后的新闻上限 |
| `state_file` | `.agent-state/hourly-crypto-perp-trader/BTCUSDT.json` | 本地状态文件；不同标的或策略应使用不同文件 |
| `allocated_balance_usdt` | `20` | 允许 agent 使用的资金上限，不是账户真实余额；例如真实余额 100、此处 20，则 agent 只能按 20 管理 |
| `live` | `false` | 只有用户明确授权才能设为 `true` |
| `max_leverage` | `1` | 硬上限；用户可显式调整 |
| `max_new_notional_pct` | `5` | 单次新增仓位名义价值占 agent 当前可用额度的最大百分比 |
| `max_risk_pct` | `1` | 有止损时，按入场价到止损价估算的单笔风险占 agent 有效额度的最大百分比 |
| `allow_short` | `true` | 是否允许开空；用户禁止时只管理现有多仓或观望 |
| `allow_long` | `true` | 是否允许开多；用户禁止时只管理现有空仓或观望 |
| `autonomous` | `true` | 无具体交易指令时自主判断；为 `false` 时只监控或执行用户明确指令 |

如果用户给出明确交易计划，优先执行该计划，但仍须检查杠杆、agent 额度、仓位上限和关键数据。用户要求突破其先前设定的上限时，以最新明确指令为准；无法确认的冲突采用更保守的解释。

## qm-cli 约定

所有用于分析的服务调用使用 `-o json`。命令失败时保留其非零状态和 stderr 摘要，不要把失败当成空数据。需要确认参数时只运行：

```bash
qm-cli help
qm-cli list
qm-cli run ohlcv --help
qm-cli run indicator --help
qm-cli run news-fetcher --help
qm-cli run binance-perp --help
qm-cli run notification --help
```

## 本地状态文件

每个周期开始先读取 `state_file`。它是 agent 的本地资金与仓位账本，用于限制资金使用、核对交易所快照和避免重复操作；不能把文件中的旧值当成无需核对的实时成交事实。

状态文件至少包含：

```json
{
  "version": 1,
  "symbol": "BTCUSDT",
  "perp_symbol": "BTC/USDT:USDT",
  "allocated_balance_usdt": 20,
  "effective_balance_usdt": 20,
  "positions": [],
  "open_orders": [],
  "recent_order_ids": [],
  "last_balance_sync_at": null,
  "updated_at": "<ISO-8601>"
}
```

字段约定：

- `allocated_balance_usdt`：用户允许 agent 使用的额度上限，只能按用户最新指令调整，不能因查到真实余额更高而自动增加。
- `effective_balance_usdt`：当前实际采用的有效额度，不超过分配上限。初始化或异常同步时，根据真实账户可用情况向下调整；真实余额充足时仍只使用分配额度。
- `positions` / `open_orders`：最近一次从交易所查询到的目标合约仓位和普通/条件挂单摘要，包含数量、方向、入场价、杠杆、订单 id、类型和状态等可用字段。
- `recent_order_ids`：本 agent 最近提交的订单 id，用于防止重复下单；不要声称记录覆盖其他工具或用户手动订单。
- `last_balance_sync_at`：最近一次确实调用 `balance` 的时间；未调用时为 `null`。

初始化和同步规则：

1. **状态文件有效**：直接采用其中的分配额度和最近记录，不调用 `balance`。本周期仍查询 `positions` 和 `open_orders`，并在结束时更新文件。
2. **文件不存在、无法解析、标的不匹配或关键字段不清楚**：调用一次 `balance`，同时查询 `positions` 和 `open_orders`，再初始化文件。有效额度不得超过用户分配上限；账户余额不足时向下调整。
3. **下单报余额不足、账户状态不一致，或精度/账户调整导致本地记录明显不可靠**：停止依赖旧文件，重新调用 `balance`、`positions` 和 `open_orders`，更新有效额度及快照。精度错误本身还应修正数量/价格，不能只更新余额后原样重试。
4. **外部账户变动**：同步只降低或确认有效额度，不得把用户未分配给 agent 的资金纳入交易。无法区分 agent 与用户手动操作时，停止新增仓位并说明冲突。
5. 每次获得新的仓位/挂单快照、收到订单回执或完成异常同步后，更新同一个文件。写文件应保留有效 JSON，避免并发周期同时写同一文件。
6. dry-run 只更新查询快照和时间，不得把预览订单写成真实订单或仓位。

agent 当前可用额度按有效额度扣除当前仓位占用保证金和挂单预留资金估算；字段不足无法可靠估算时，不新增仓位，并按上述规则同步。任何 sizing 都不能使用超出 `effective_balance_usdt` 的账户资金。

## 单个交易周期

### 1. 读取状态并获取数据快照

先按上节读取状态文件。状态有效时，可并行运行以下只读命令。示例使用默认值，实际执行时替换为用户配置，尤其是两处 `interval` 必须一致。

行情：

```bash
qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h --limit 200 -o json
```

`patterns: ALL` 必须展开为以下全部 TA-Lib K 线形态，不得用 `ALL` 作为命令参数，也不能因输出较长而自行删减：

```text
2CROWS,3BLACKCROWS,3INSIDE,3LINESTRIKE,3OUTSIDE,3STARSINSOUTH,3WHITESOLDIERS,ABANDONEDBABY,ADVANCEBLOCK,BELTHOLD,BREAKAWAY,CLOSINGMARUBOZU,CONCEALBABYSWALL,COUNTERATTACK,DARKCLOUDCOVER,DOJI,DOJISTAR,DRAGONFLYDOJI,ENGULFING,EVENINGDOJISTAR,EVENINGSTAR,GAPSIDESIDEWHITE,GRAVESTONEDOJI,HAMMER,HANGINGMAN,HARAMI,HARAMICROSS,HIGHWAVE,HIKKAKE,HIKKAKEMOD,HOMINGPIGEON,IDENTICAL3CROWS,INNECK,INVERTEDHAMMER,KICKING,KICKINGBYLENGTH,LADDERBOTTOM,LONGLEGGEDDOJI,LONGLINE,MARUBOZU,MATCHINGLOW,MATHOLD,MORNINGDOJISTAR,MORNINGSTAR,ONNECK,PIERCING,RICKSHAWMAN,RISEFALL3METHODS,SEPARATINGLINES,SHOOTINGSTAR,SHORTLINE,SPINNINGTOP,STALLEDPATTERN,STICKSANDWICH,TAKURI,TASUKIGAP,THRUSTING,TRISTAR,UNIQUE3RIVER,UPSIDEGAP2CROWS,XSIDEGAP3METHODS
```

技术指标命令（若用户明确设置 `patterns` 为空则省略 `--patterns`；若给出自定义列表则替换）：

```bash
qm-cli run indicator --symbol BTCUSDT --market crypto --interval 1h --limit 200 --indicators sma,ema,macd,rsi,boll,atr --patterns 2CROWS,3BLACKCROWS,3INSIDE,3LINESTRIKE,3OUTSIDE,3STARSINSOUTH,3WHITESOLDIERS,ABANDONEDBABY,ADVANCEBLOCK,BELTHOLD,BREAKAWAY,CLOSINGMARUBOZU,CONCEALBABYSWALL,COUNTERATTACK,DARKCLOUDCOVER,DOJI,DOJISTAR,DRAGONFLYDOJI,ENGULFING,EVENINGDOJISTAR,EVENINGSTAR,GAPSIDESIDEWHITE,GRAVESTONEDOJI,HAMMER,HANGINGMAN,HARAMI,HARAMICROSS,HIGHWAVE,HIKKAKE,HIKKAKEMOD,HOMINGPIGEON,IDENTICAL3CROWS,INNECK,INVERTEDHAMMER,KICKING,KICKINGBYLENGTH,LADDERBOTTOM,LONGLEGGEDDOJI,LONGLINE,MARUBOZU,MATCHINGLOW,MATHOLD,MORNINGDOJISTAR,MORNINGSTAR,ONNECK,PIERCING,RICKSHAWMAN,RISEFALL3METHODS,SEPARATINGLINES,SHOOTINGSTAR,SHORTLINE,SPINNINGTOP,STALLEDPATTERN,STICKSANDWICH,TAKURI,TASUKIGAP,THRUSTING,TRISTAR,UNIQUE3RIVER,UPSIDEGAP2CROWS,XSIDEGAP3METHODS -o json
```

Crypto 与宏观相关新闻：

```bash
qm-cli run news-fetcher --mode recent --sources cls,em,sina,ths,futu --keywords crypto,cryptocurrency,加密货币,数字货币,比特币,BTC,以太坊,稳定币,ETF,SEC,监管,黑客,清算,美联储,降息,加息 --keyword-match any --limit 50 -o json
```

当前合约状态（默认不运行 `balance`）：

```bash
qm-cli run binance-perp positions --symbol BTC/USDT:USDT -o json
qm-cli run binance-perp open_orders --symbol BTC/USDT:USDT --include-conditional -o json
```

只有满足状态文件初始化/异常同步条件时才额外运行：

```bash
qm-cli run binance-perp balance -o json
```

检查：

- 记录本周期时间、K 线最新时间、指标、新闻实际覆盖时间、agent 有效额度、仓位方向/数量/入场价/杠杆，以及普通和条件挂单。
- 对返回的每项指标和每种 K 线形态检查是否存在单项 `error`；整体命令成功不代表所有计算都有效。部分形态没有信号是正常结果，不等于计算失败。
- 新闻服务可能部分来源成功；将 `errors` 视为需要通知的报错，并明确哪些来源缺失。新闻不是固定时间窗口，不得声称覆盖某个固定时段，除非实际时间戳支持。
- 对重复新闻按 id/URL 和内容语义去重，区分已确认事实、市场评论和未证实消息；不要把单条新闻当成确定交易信号。
- 保存本周期初始仓位和挂单快照，供执行后比较，并在周期结束时写回状态文件。

### 2. 综合判断

先风控，后信号。只有数据充分、方向允许、账户状态明确且收益风险比合理时才考虑交易；信号冲突、波动异常、重大未证实新闻或无法合理 sizing 时选择 `HOLD`。

综合以下信息，不依赖单一指标或形态：

- SMA/EMA 的位置与斜率、价格相对均线的位置，用于判断趋势。
- MACD 的方向和变化、RSI 是否过热/超卖，用于判断动能；强趋势中不能仅因超买超卖就逆势。
- BOLL 的位置/扩张和 ATR，用于评估波动、止损距离与仓位；ATR 上升本身不是方向信号。
- 全部 K 线形态用于发现共振和冲突，只作辅助，须结合趋势和成交量；不要堆砌无信号形态，也不要把形态数量直接当成胜率。
- 新闻用于识别事件风险与潜在催化，不根据标题情绪机械追涨杀跌。
- 当前仓位、未实现盈亏、已有止损/止盈和挂单，避免重复开仓、重复挂单或与保护单冲突。

自主决策输出 `LONG`、`SHORT`、`REDUCE`、`CLOSE`、`CANCEL/REPLACE` 或 `HOLD`，并简述主要依据和使信号失效的条件。用户给出了具体计划时，改为核对该计划是否仍可安全执行。

仓位 sizing：

1. 使用状态文件中的 agent 有效/可用额度和最新价格估算，不默认查询真实余额，也不假设最低下单量、数量精度或价格精度一定通过交易所校验。
2. 新增名义价值不得超过 `agent可用额度 × max_new_notional_pct / 100`，也不得导致设置杠杆超过 `max_leverage`。
3. 有明确止损时，再确保 `abs(入场价 - 止损价) × 数量 <= agent有效额度 × max_risk_pct / 100`，数量向下取可满足精度要求的值。
4. 数量必须为正且满足交易所限制；无法确认或金额过小时不交易，不通过提高杠杆或动用未分配余额来绕过限制。
5. 一个周期原则上只执行一个主要仓位调整及其必要保护单，避免连续下单放大风险。

减仓/平仓使用 `--reduce-only` 或合适的 `--close-position`，不得意外反向开仓。新开仓应评估并尽量设置与 ATR/结构相符的保护性止损；保护单与已有订单冲突时先停止并说明。不要自动更改全仓/逐仓模式或单向/双向持仓模式。

### 3. dry-run 或实盘执行

`live: false` 时，写操作只 dry-run。例如调整杠杆和开多：

```bash
qm-cli run binance-perp set_leverage --symbol BTC/USDT:USDT --leverage 1 --dry-run -o json
qm-cli run binance-perp create_order --symbol BTC/USDT:USDT --side buy --order-type market --amount 0.001 --dry-run -o json
```

检查 preview 的 action、合约、方向、类型、数量、价格/止损价、`reduce_only`、`position_side` 等完全符合决策。preview 仅表示请求计划，不表示交易所已接受或成交。结果必须标注“计划/预览，未下单”。

`live: true` 时，完成本地参数和风控检查后直接使用 `--live`，**不先执行 dry-run**：

```bash
qm-cli run binance-perp set_leverage --symbol BTC/USDT:USDT --leverage 1 --live -o json
qm-cli run binance-perp create_order --symbol BTC/USDT:USDT --side buy --order-type market --amount 0.001 --live -o json
```

其他实盘写操作同样直接使用 `qm-cli run binance-perp create_order|cancel_order ... --live`。不要重试已经返回交易所订单 id 的请求。若失败且没有订单 id，也必须先按错误规则核对状态；只有确认交易所未接受原请求且修正了失败原因，才可决定是否提交修正后的订单。

### 4. 执行后复查并更新状态

发生任何实盘写操作后，重新查询：

```bash
qm-cli run binance-perp positions --symbol BTC/USDT:USDT -o json
qm-cli run binance-perp open_orders --symbol BTC/USDT:USDT --include-conditional -o json
```

将结果与初始快照比较并更新 `state_file`：

- 区分“订单已提交”“挂单中”“部分成交”“已成交”和“仓位已变化”；仅凭下单成功不能声称成交。
- 若订单被接受但尚未成交，通知中准确说明挂单状态，并把订单 id 和快照写入状态文件。
- 若状态不明，停止本周期后续写操作，按错误处理，不盲目补单。
- dry-run 不需要把预览当成仓位调整通知，也不能把预览写入真实仓位。

## 通知与错误处理

以下情况必须尝试通知：

- 实盘订单提交、撤单、杠杆调整或实际仓位变化。
- 任一 `qm-cli` 服务报错，包括新闻部分来源失败、指标或形态单项错误、下单失败、复查失败。
- 状态文件损坏/不一致导致同步，以及数据过期或关键数据不足导致跳过交易；无需对普通的 `HOLD` 通知。

仓位/订单调整通知示例：

```bash
qm-cli run notification --title "BTCUSDT 永续仓位调整" --content "时间：<ISO时间>\n动作：<提交/撤单/杠杆/仓位变化>\n订单：<id、方向、类型、数量、价格>\n状态：<已提交/挂单/成交/部分成交>\n调整前后仓位：<摘要>\nagent额度：<有效额度与可用额度>\n依据：<简要依据>" --format markdown -o json
```

错误通知示例：

```bash
qm-cli run notification --title "BTCUSDT 交易周期报错" --content "时间：<ISO时间>\n服务：<ohlcv/indicator/news-fetcher/binance-perp/notification>\n操作：<action>\n错误：<stderr 或结构化错误摘要>\n处理：<已停止新开仓/未提交实盘订单/状态待确认>\n注意：不包含任何凭据。" --format markdown -o json
```

错误处理规则：

- 关键数据失败：停止新增/扩仓；已有仓位和保护单保持原状，除非用户有明确的风险处置指令且所需账户数据仍可靠。
- 余额不足或账户状态不一致：按状态文件规则调用 `balance` 并同步仓位/挂单，更新有效额度；不得通过增加 `allocated_balance_usdt` 解决。
- 数量或价格精度错误：修正参数并核对交易所未接受原请求；不得原样盲目重试。
- 新闻失败：记录缺失，不因新闻不完整而放大仓位；按“报错”通知。
- 写操作失败：不再执行依赖它的后续订单，通知失败参数的安全摘要和当前已知状态。
- 状态文件写入失败：停止后续写操作并通知，避免无本地账本继续交易。
- 通知失败：不能假装已送达；在周期结果中直接告诉用户原始事件和通知失败原因。
- 如果 qm-cli 本身不可用，无法调用通知服务时，直接在结果中报告阻塞，不要改用其他交易或通知工具。

## 周期结果

每个周期结束给用户一个简短结果：

- 标的、K 线 `interval`、模式和数据时间。
- 趋势/动能/波动、有效 K 线形态与新闻的一两句摘要。
- agent 有效额度和可用额度；没有调用 `balance` 时不必提及真实账户余额。
- 决策及理由；无交易时明确 `HOLD`。
- dry-run 预览或实盘订单状态，以及调整后的仓位/挂单。
- 状态文件路径和更新结果，以及错误和通知送达状态；没有错误时不展开。

不得在周期结果中承诺收益、隐瞒 dry-run 与实盘的差别，或把计划、订单提交和实际成交混为一谈。
