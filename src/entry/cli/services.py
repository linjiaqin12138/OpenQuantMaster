from __future__ import annotations

import asyncio
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from src.config import load_config
from src.entry.cli.base import echo_service_result, register_cli
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
@click.command()
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
@click.option(
    "--output",
    "-o",
    default="rich",
    show_default=True,
    help="Output format: rich, json, or jsonpath=<expression>.",
)
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
    """Fetch OHLCV bars."""
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
