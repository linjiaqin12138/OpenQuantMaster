from __future__ import annotations

import asyncio
import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from src.config import load_config
from src.entry.cli.base import echo_service_result, output_option, register_cli
from src.services.indicator import Indicator
from src.services.ohlcv import OHLCV, OHLCVConfig


def render_indicator(data: dict[str, Any]) -> None:
    console = Console()
    console.print(f"[bold]{data['summary']}[/bold]")
    table = Table(show_lines=False)
    table.add_column("Indicator")
    table.add_column("Values")
    table.add_column("Parameters")
    for name, values in data["indicators"].items():
        params = values.get("params", {})
        display_values = {key: value for key, value in values.items() if key != "params"}
        table.add_row(name, json.dumps(display_values, ensure_ascii=False), json.dumps(params))
    console.print(table)
    patterns = data["patterns"]
    if patterns:
        console.print(
            f"Last bullish: {patterns.get('last_bullish') or '-'}; "
            f"last bearish: {patterns.get('last_bearish') or '-'}; "
            f"history: {len(patterns.get('history', []))}"
        )


@register_cli(renderer=render_indicator)
@click.command(
    epilog="""
\b
Examples:
  qm-cli run indicator --symbol BTCUSDT --indicators sma,rsi,macd
  qm-cli run indicator --symbol BTCUSDT --indicator-params '{"SMA":{"timeperiod":20}}'
  qm-cli run indicator --symbol BTCUSDT --patterns DOJI,ENGULFING -o rich
  qm-cli run indicator --symbol BTCUSDT -o 'jsonpath={.indicators.rsi.value}'

Indicator aliases: sma, ema, macd, rsi, boll, atr. Other TA-Lib function names are accepted.
""",
)
@click.option("--symbol", required=True, help="Ticker, for example BTCUSDT or AAPL.")
@click.option(
    "--market",
    default="crypto",
    show_default=True,
    type=click.Choice(["crypto", "us_equity", "hk_equity", "a_share"]),
)
@click.option("--interval", default="1h", show_default=True)
@click.option("--limit", default=100, show_default=True, type=int)
@click.option(
    "--indicators",
    default="sma,ema,macd,rsi,boll,atr",
    show_default=True,
    help="Comma-separated indicator names.",
)
@click.option("--indicator-params", default="{}", help="JSON object of per-indicator parameters.")
@click.option("--patterns", help="Comma-separated candlestick pattern names.")
@output_option
@click.pass_context
def indicator(
    ctx: click.Context,
    symbol: str,
    market: str,
    interval: str,
    limit: int,
    indicators: str,
    indicator_params: str,
    patterns: str | None,
    output: str,
) -> None:
    """Fetch OHLCV data and compute technical indicators.

    --indicators and --patterns accept comma-separated names. --indicator-params
    is a JSON object keyed by indicator name, for example '{"SMA":{"timeperiod":20}}'.
    Enough bars are required for the longest indicator lookback; increase --limit
    if the service reports insufficient data.
    """
    try:
        config = load_config(ctx.obj["config_path"])
        params = json.loads(indicator_params)
        if not isinstance(params, dict):
            raise ValueError("indicator params must be a JSON object")
    except (RuntimeError, json.JSONDecodeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    ohlcv_service = OHLCV(OHLCVConfig.from_config(config))
    result = asyncio.run(
        Indicator(ohlcv=ohlcv_service).run(
            {
                "symbol": symbol,
                "market": market,
                "interval": interval,
                "limit": limit,
                "indicators": [value.strip() for value in indicators.split(",") if value.strip()],
                "indicator_params": params,
                "patterns": [value.strip() for value in patterns.split(",") if value.strip()]
                if patterns
                else None,
            }
        )
    )
    echo_service_result(result, "indicator", output)
