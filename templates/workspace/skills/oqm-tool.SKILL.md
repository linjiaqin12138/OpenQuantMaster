---
name: oqm-tool
description: How to call OpenQuantMaster pipeline tools from the shell. Use when a task needs data fetching, signal scanning, backtesting, notifications, or any other registered OpenQuantMaster tool.
---

# Calling OpenQuantMaster tools

All registered tools are invoked through the runtime CLI:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json>'
```

Rules:

- The command prints a JSON `ToolResult` to stdout. Always check the `success` field before using `data`.
- Tool input schemas live in `tools/<domain>/<tool_name>.py` (the `input_model` class). Read the source if unsure about parameters.
- Currently registered tools include: `demo_data_tool`, `notify_tool`, `ohlcv_tool`, `signal_scan_tool`, `backtest_tool`, `agent_tool`.

Examples:

```bash
python -m runtime.cli tool ohlcv_tool --inputs '{"symbol":"BTC/USDT","timeframe":"1h","limit":100}'
python -m runtime.cli tool notify_tool --inputs '{"subject":"Report","body":"...","channels":["pushplus"]}'
```
