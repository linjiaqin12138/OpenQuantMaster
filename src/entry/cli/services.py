from __future__ import annotations

import asyncio

import click

from src.config import load_config
from src.entry.cli.base import echo_service_result, register_cli
from src.services.ohlcv import OHLCV
from src.services.ohlcv import load_config as load_ohlcv_config


@register_cli
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
) -> None:
    """Fetch OHLCV bars and print the result as JSON."""
    try:
        config = load_config(ctx.obj["config_path"])
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    result = asyncio.run(
        OHLCV(load_ohlcv_config(config)).run(
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
    echo_service_result(result)
