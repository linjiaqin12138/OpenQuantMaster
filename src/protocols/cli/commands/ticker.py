from __future__ import annotations

from typing import Any

import click
from rich.console import Console

from src.composition import build_ticker_service
from src.config import load_config
from src.protocols.cli.base import echo_service_result, output_option, run_service


def render_ticker(data: dict[str, Any]) -> None:
    console = Console()
    change = _format_number(data["change"])
    change_percent = data["change_percent"]
    percent = f"{change_percent:+.2f}%" if change_percent is not None else "-"
    console.print(
        f"[bold]{data['symbol']}[/bold] {data['name']} "
        f"[dim]({data['source']})[/dim]"
    )
    console.print(
        f"Price: {data['price']}  Change: {change} ({percent})  "
        f"Previous close: {_format_number(data['previous_close'])}"
    )
    console.print(
        f"Open: {_format_number(data['open'])}  "
        f"High: {_format_number(data['high'])}  "
        f"Low: {_format_number(data['low'])}"
    )
    console.print(
        f"[dim]Quote time: {data['quote_time'] or '-'}  "
        f"Fetched at: {data['fetched_at']}[/dim]"
    )


def _format_number(value: float | None) -> str:
    return "-" if value is None else f"{value:+.2f}"


@click.command(
    epilog="""
\b
Examples:
  qm-cli run ticker --symbol 600519.SH --market a_share
  qm-cli run ticker --symbol 515070 --market a_share -o json
  qm-cli run ticker --symbol BTC/USDT --market crypto -o json

A-share codes may omit the exchange suffix; it is derived from the code and
confirmed against the data source. The crypto venue follows the configured
Binance provider settings.
JSON output contains only the service data and can be piped to a file.
""",
)
@click.option("--symbol", required=True, help="Ticker, for example 600519.SH or BTC/USDT.")
@click.option(
    "--market",
    required=True,
    type=click.Choice(["a_share", "crypto"]),
    help="Market of the ticker.",
)
@output_option
@click.pass_context
def ticker(ctx: click.Context, symbol: str, market: str, output: str) -> None:
    """Fetch the latest ticker snapshot of one instrument.

    A-shares are read through Tushare and crypto symbols through the configured
    CCXT venue. The response keeps the provider quote time separate from the
    local fetch time. This is a point-in-time snapshot, not a stream.
    """
    try:
        config = load_config(ctx.obj["config_path"])
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    result = run_service(
        build_ticker_service(config).fetch_ticker(
            {"symbol": symbol, "market": market}
        ),
        output=output,
    )
    echo_service_result(result, "ticker", output)
