from __future__ import annotations

import asyncio
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from src.config import load_config
from src.entry.cli.base import echo_service_result, output_option, register_cli
from src.services.ohlcv import OHLCV, OHLCVConfig


def render_ohlcv(data: dict[str, Any]) -> None:
    console = Console()
    console.print(
        f"[bold]{data['symbol']}[/bold] {data['market']} {data['interval']} "
        f"[dim]({data['rows']} rows)[/dim]"
    )
    bars = data["bars"]
    if not bars:
        console.print("No bars returned.")
        return

    table = Table(show_lines=False)
    for column in ("Timestamp", "Open", "High", "Low", "Close", "Volume"):
        table.add_column(column)
    for bar in bars:
        table.add_row(*(str(bar[key]) for key in ("timestamp", "open", "high", "low", "close", "volume")))
    console.print(table)


@register_cli(renderer=render_ohlcv)
@click.command(
    epilog="""
\b
Examples:
  qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h --limit 30
  qm-cli run ohlcv --symbol AAPL --market us_equity --interval 1d --start 2026-01-01
  qm-cli run ohlcv --symbol 000001.SZ --market a_share --interval 1d --source akshare
  qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1d -o 'jsonpath={.bars}'

Dates use ISO-8601. JSON output contains only the service data and can be piped to a file.
""",
)
@click.option("--symbol", required=True, help="Ticker, for example BTCUSDT or AAPL.")
@click.option(
    "--market",
    required=True,
    type=click.Choice(["crypto", "us_equity", "hk_equity", "a_share"]),
    help="Market of the ticker.",
)
@click.option("--interval", required=True, help="Bar interval, for example 1h or 1d.")
@click.option("--start", help="Inclusive start time in ISO-8601 format.")
@click.option("--end", help="Inclusive end time in ISO-8601 format.")
@click.option("--limit", default=1000, show_default=True, type=int, help="Maximum number of bars.")
@click.option(
    "--source",
    type=click.Choice(["ccxt", "yfinance", "tushare", "akshare"]),
    help="Force a market data provider.",
)
@output_option
@click.pass_context
def ohlcv(
    ctx: click.Context,
    symbol: str,
    market: str,
    interval: str,
    start: str | None,
    end: str | None,
    limit: int,
    source: str | None,
    output: str,
) -> None:
    """Fetch Open, High, Low, Close and Volume bars.

    MARKET selects the default provider: crypto uses CCXT, US/HK equities use
    yfinance, and A-shares use Tushare or AkShare. --source overrides that
    selection. --start/--end optionally restrict the time range, while --limit
    controls the requested row count (1-5000).
    """
    try:
        config = load_config(ctx.obj["config_path"])
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    result = asyncio.run(
        OHLCV(OHLCVConfig.from_config(config)).run(
            {
                "symbol": symbol,
                "market": market,
                "interval": interval,
                "start": start,
                "end": end,
                "limit": limit,
                "source": source,
            }
        )
    )
    echo_service_result(result, "ohlcv", output)
