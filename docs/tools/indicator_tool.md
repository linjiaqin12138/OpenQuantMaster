# indicator_tool

基于 OHLCV 数据计算任意 TA-Lib 技术指标并识别蜡烛图形态，输出汇总结论与指标结果 artifact。

## 支持的指标

`indicators` 接受任意 TA-Lib 函数名（大小写不敏感）。工具通过 `talib.abstract.Function` 统一动态分发，不再为单个指标保留专用计算逻辑。

为兼容旧用法，以下 6 个友好别名仍被支持，并映射到对应 TA-Lib 函数：

| 别名 | TA-Lib 函数 | 说明 |
|------|-------------|------|
| `sma` | `SMA` | 简单移动平均线 |
| `ema` | `EMA` | 指数移动平均线 |
| `macd` | `MACD` | 指数平滑异同移动平均线 |
| `rsi` | `RSI` | 相对强弱指数 |
| `boll` | `BBANDS` | 布林带 |
| `atr` | `ATR` | 真实波动幅度均值 |

未传 `indicators` 时，默认计算上述 6 个指标。传入不存在的函数名将返回 `ToolResult(success=False)`。

## 支持的蜡烛图形态

`patterns` 为 `list[str] | None`，默认 `None`（不计算形态）。传入列表时启用形态识别，支持 TA-Lib 全部 61 个 `CDL*` 函数。

- 可传裸名，自动补 `CDL` 前缀，如 `["ENGULFING", "DOJI"]` 等价于 `["CDLENGULFING", "CDLDOJI"]`。
- 也可直接传完整名如 `"CDLENGULFING"`。
- 形态方向默认按 TA-Lib 返回值符号判定：`>0` 为 `bullish`（看涨），`<0` 为 `bearish`（看跌）。
- `DOJI`、`LONGLEGGEDDOJI`、`SPINNINGTOP`、`HIKKAKE` 等非零但语义中性的形态会被覆盖标记为 `neutral`。

## 输入参数

| 参数名 | 类型 | 必填 | 默认值 | 说明 |
|--------|------|------|--------|------|
| source | string | 否 | `"symbol"` | 数据来源，可选 `"symbol"` 或 `"ohlcv_artifact"` |
| symbol | string | 条件必填 | `null` | 交易标的代码，`source="symbol"` 时必填 |
| market | string | 否 | `"crypto"` | 市场类型，可选 `"crypto"、`"us_equity"`、`"hk_equity"`、`"a_share"` |
| interval | string | 否 | `"1h"` | K 线周期 |
| limit | integer | 否 | `100` | 请求的 K 线数量，必须 ≥ 1 |
| indicators | list[string] | 否 | `["sma", "ema", "macd", "rsi", "boll", "atr"]` | 要计算的指标函数名列表 |
| indicator_params | dict[str, dict] | 否 | `{}` | 按函数名（或别名）索引，覆盖 TA-Lib 默认参数，如 `{"SMA": {"timeperiod": 20}}` |
| patterns | list[string] | 否 | `None` | 要识别的蜡烛图形态裸名/全名列表，`None` 或空列表表示不计算 |
| artifact | string | 条件必填 | `null` | OHLCV artifact 相对路径或绝对路径，`source="ohlcv_artifact"` 时必填 |
| pipeline_run_id | string | 否 | `null` | Pipeline 运行 ID，用于组织输出 artifact 目录 |

## 输出结构

成功时 `ToolResult.data` 包含以下字段：

```json
{
  "symbol": "SUIUSDT",
  "interval": "1h",
  "rows": 100,
  "indicators": {
    "sma": {
      "value": 0.71626,
      "params": { "timeperiod": 30 }
    },
    "ema": {
      "value": 0.71654,
      "params": { "timeperiod": 30 }
    },
    "macd": {
      "macd": 0.00125,
      "macdsignal": 0.00089,
      "macdhist": 0.00036,
      "params": { "fastperiod": 12, "slowperiod": 26, "signalperiod": 9 }
    },
    "rsi": {
      "value": 54.65,
      "params": { "timeperiod": 14 }
    },
    "boll": {
      "upperband": 0.72306,
      "middleband": 0.71626,
      "lowerband": 0.70946,
      "params": { "timeperiod": 5 }
    },
    "atr": {
      "value": 0.00375,
      "params": { "timeperiod": 14 }
    }
  },
  "patterns": {
    "last_bullish": "ENGULFING",
    "last_bearish": "GRAVESTONEDOJI",
    "history": [
      {
        "timestamp": "2026-07-22T13:00:00+00:00",
        "pattern": "ENGULFING",
        "label": "bullish",
        "strength": 80
      }
    ]
  },
  "summary": "SUIUSDT 1h | SMA(30)=0.7163 RSI(14)=54.7 MACD.hist=0.00036 | 形态: 看涨 ENGULFING",
  "artifact": "<run_id>/indicator_tool/indicator_result.json"
}
```

说明：

- 单输出指标输出 `{"value": ..., "params": {...}}`。
- 多输出指标按 `output_names` 展开（如 `MACD` 输出 `macd`、`macdsignal`、`macdhist`），并附加 `params`。
- 运行时失败的指标（如缺少必需输入的 `MAVP`）记录 `{"error": "..."}`，但整体 `success=true`。
- `patterns` 为 `{}` 时表示未启用形态识别。

输出 artifact 为 JSON 文件，存储于 `artifacts/<run_id>/indicator_tool/indicator_result.json`，包含与 `data` 中一致的完整内容。

## CLI 使用示例

### 1. 直接通过 symbol 计算默认指标

```bash
python -m runtime.cli tool indicator_tool --inputs '{"symbol": "SUIUSDT", "market": "crypto", "interval": "1h", "limit": 100}'
```

### 2. 指定任意 TA-Lib 指标并覆盖参数

```bash
python -m runtime.cli tool indicator_tool --inputs '{"symbol": "SUIUSDT", "market": "crypto", "interval": "1h", "indicators": ["ADX", "OBV", "STOCH"], "indicator_params": {"STOCH": {"fastk_period": 14, "slowk_period": 3, "slowd_period": 3}}}'
```

### 3. 指定形态识别

```bash
python -m runtime.cli tool indicator_tool --inputs '{"symbol": "SUIUSDT", "market": "crypto", "interval": "1h", "indicators": ["rsi", "macd"], "patterns": ["ENGULFING", "DOJI"]}'
```

### 4. 从 artifact 读取（pipeline 场景）

```bash
python -m runtime.cli tool indicator_tool --inputs '{"source": "ohlcv_artifact", "artifact": "run-xxx/ohlcv_tool/ohlcv_SUIUSDT_1h.csv", "indicators": ["sma", "ema", "boll"], "patterns": ["HAMMER", "ENGULFING"]}'
```

> 注意：`artifact` 路径可以是相对于 `artifacts/` 目录的相对路径，也可以是绝对路径。

## Pipeline YAML 使用示例

```yaml
name: indicator_demo

trigger:
  type: manual

stages:
  - fetch_ohlcv:
      tool: ohlcv_tool
      inputs:
        symbol: SUIUSDT
        market: crypto
        interval: 1h
        limit: 100

  - compute_indicators:
      tool: indicator_tool
      inputs:
        source: ohlcv_artifact
        artifact: "$fetch_ohlcv.out.artifact"
        indicators:
          - sma
          - ema
          - macd
          - rsi
          - boll
          - atr
        indicator_params:
          SMA:
            timeperiod: 20
          RSI:
            timeperiod: 14
        patterns:
          - ENGULFING
          - DOJI
```

## 依赖说明

`indicator_tool` 依赖 Python 包 `ta-lib`（通过 `import talib` 调用）。

- `ta-lib` 需要 TA-Lib C 库支持。在 Linux/macOS 上通常需要先安装系统库（如 `ta-lib`），再 `pip install TA-Lib`。
- 部分平台提供预编译 wheel（例如 `ta-lib-bin`、`TA-Lib-Precompiled` 等），可直接 `pip install`。
- 如果 `ta-lib` 安装失败，指标计算功能将无法使用。

## 注意事项

1. **数据量要求**：工具要求至少 2 行 OHLCV 数据，且实际行数必须满足所选指标/形态的最大 `talib.abstract.Function.lookback`。不同函数所需行数不同，传入 `limit=200` 通常可覆盖绝大多数指标。
2. **小数精度**：指标值以 `float` 输出，可能因浮点运算产生微小精度差异。
3. **形态识别说明**：形态基于 TA-Lib 的整数编码结果判断，`strength` 为 TA-Lib 返回值的绝对值；方向按符号判定，中性形态见上文覆盖表。
4. **symbol 推断**：从 artifact 读取时，工具会尝试根据文件名推断 `symbol`（例如 `ohlcv_BTC-USDT.csv` 推断为 `BTC-USDT`）。
5. **默认值**：未传 `indicators` 时默认计算 6 个指标；未传 `patterns` 时默认不启用形态识别。
