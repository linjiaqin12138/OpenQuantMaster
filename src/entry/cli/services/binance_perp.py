from __future__ import annotations

import asyncio
import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from src.config import load_config
from src.entry.cli.base import echo_service_result, output_option, register_cli
from src.services.binance_perp import BinancePerp, BinancePerpConfig


def render_binance_perp(data: dict[str, Any]) -> None:
    console = Console()
    console.print(
        f"[bold]{data['action']}[/bold] {data['exchange']}/{data['product']} "
        f"dry_run={data['dry_run']} sandbox={data['sandbox']}"
    )
    if data["planned"] is not None:
        table = Table("Field", "Value")
        for key, value in data["planned"].items():
            table.add_row(key, json.dumps(value, ensure_ascii=False))
        console.print(table)
        return

    result = data["result"]
    if data["action"] == "balance":
        table = Table("Asset", "Free", "Used", "Total")
        for asset, values in result["assets"].items():
            table.add_row(asset, str(values["free"]), str(values["used"]), str(values["total"]))
        console.print(table)
    elif isinstance(result, list):
        if not result:
            console.print("No results returned.")
            return
        columns = list(result[0])
        table = Table(*(column for column in columns))
        for row in result:
            table.add_row(*(json.dumps(row.get(column), ensure_ascii=False) for column in columns))
        console.print(table)
    elif isinstance(result, dict):
        table = Table("Field", "Value")
        for key, value in result.items():
            table.add_row(key, json.dumps(value, ensure_ascii=False))
        console.print(table)


@register_cli(renderer=render_binance_perp)
@click.command(
    "binance-perp",
    epilog="""
\b
Examples:
  qm-cli run binance-perp balance
  qm-cli run binance-perp positions --symbol BTC/USDT:USDT
  qm-cli run binance-perp open_orders --exclude-conditional
  qm-cli run binance-perp create_order --symbol BTC/USDT:USDT --side buy --order-type market --amount 0.001
  qm-cli run binance-perp set_leverage --symbol BTC/USDT:USDT --leverage 5
  qm-cli run binance-perp cancel_order --symbol BTC/USDT:USDT --order-id 12345 --live

Write actions default to dry-run and never submit requests. Use --live explicitly to execute them.
""",
)
@click.argument(
    "action",
    type=click.Choice(
        [
            "balance",
            "positions",
            "open_orders",
            "create_order",
            "cancel_order",
            "set_leverage",
            "set_margin_mode",
            "set_position_mode",
        ]
    ),
)
@click.option("--symbol", help="Perpetual symbol, for example BTC/USDT:USDT.")
@click.option("--side", type=click.Choice(["buy", "sell"]))
@click.option(
    "--order-type",
    type=click.Choice(
        ["market", "limit", "stop_market", "take_profit_market", "stop", "take_profit", "trailing_stop_market"]
    ),
)
@click.option("--amount", type=float)
@click.option("--price", type=float)
@click.option("--stop-price", type=float)
@click.option("--callback-rate", type=float)
@click.option("--activation-price", type=float)
@click.option("--order-id")
@click.option("--leverage", type=int)
@click.option("--margin-mode", type=click.Choice(["isolated", "cross"]))
@click.option("--reduce-only", is_flag=True)
@click.option("--close-position", is_flag=True)
@click.option("--position-side", type=click.Choice(["BOTH", "LONG", "SHORT"]))
@click.option("--working-type", type=click.Choice(["CONTRACT_PRICE", "MARK_PRICE"]))
@click.option("--hedge/--one-way", default=None, help="Set hedge or one-way position mode.")
@click.option("--include-conditional/--exclude-conditional", default=True, show_default=True)
@click.option("--dry-run/--live", default=True, show_default=True, help="Preview writes or execute live.")
@output_option
@click.pass_context
def binance_perp(
    ctx: click.Context,
    action: str,
    symbol: str | None,
    side: str | None,
    order_type: str | None,
    amount: float | None,
    price: float | None,
    stop_price: float | None,
    callback_rate: float | None,
    activation_price: float | None,
    order_id: str | None,
    leverage: int | None,
    margin_mode: str | None,
    reduce_only: bool,
    close_position: bool,
    position_side: str | None,
    working_type: str | None,
    hedge: bool | None,
    include_conditional: bool,
    dry_run: bool,
    output: str,
) -> None:
    """Query or trade Binance USDT-M perpetual futures.

    ACTION selects the operation. Read actions contact the exchange immediately.
    Write actions validate and preview their payload by default; --live submits
    them. Credentials come from providers.binance in the resolved YAML config.
    Symbol format follows CCXT, for example BTC/USDT:USDT.
    """
    try:
        config = load_config(ctx.obj["config_path"])
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    result = asyncio.run(
        BinancePerp(BinancePerpConfig.from_config(config)).run(
            {
                "action": action,
                "dry_run": dry_run,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": amount,
                "price": price,
                "stop_price": stop_price,
                "callback_rate": callback_rate,
                "activation_price": activation_price,
                "order_id": order_id,
                "leverage": leverage,
                "margin_mode": margin_mode,
                "reduce_only": reduce_only,
                "close_position": close_position,
                "position_side": position_side,
                "working_type": working_type,
                "hedge": hedge,
                "include_conditional": include_conditional,
            }
        )
    )
    echo_service_result(result, "binance-perp", output)
