from __future__ import annotations

import json
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from src.composition import build_binance_perp_service
from src.config import load_config
from src.protocols.cli.base import echo_service_result, output_option, run_service


def render_binance_perp(data: dict[str, Any]) -> None:
    console = Console()
    if "assets" in data:
        table = Table("Asset", "Free", "Used", "Total")
        for asset, values in data["assets"].items():
            table.add_row(asset, str(values["free"]), str(values["used"]), str(values["total"]))
        console.print(table)
        return

    if "dry_run" in data:
        console.print(f"[bold]dry_run={data['dry_run']}[/bold]")
        payload = data.get("planned") or data.get("order") or data.get("result")
        if payload is None:
            console.print("No payload returned.")
            return
        table = Table("Field", "Value")
        for key, value in payload.items():
            table.add_row(key, json.dumps(value, ensure_ascii=False))
        console.print(table)
        return

    for key in ("positions", "orders"):
        rows = data.get(key)
        if rows is None:
            continue
        if not rows:
            console.print("No results returned.")
            return
        columns = list(rows[0])
        table = Table(*columns)
        for row in rows:
            table.add_row(*(json.dumps(row.get(column), ensure_ascii=False) for column in columns))
        console.print(table)
        return

    table = Table("Field", "Value")
    for key, value in data.items():
        table.add_row(key, json.dumps(value, ensure_ascii=False))
    console.print(table)


@click.command(
    "binance-perp",
    epilog="""
\b
Examples:
  qm-cli run binance-perp balance
  qm-cli run binance-perp positions --symbol BTC/USDT:USDT
  qm-cli run binance-perp open_orders --symbol BTC/USDT:USDT --exclude-conditional
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

    service = build_binance_perp_service(config)
    if action == "balance":
        call = service.balance()
    elif action == "positions":
        call = service.positions({"symbol": symbol})
    elif action == "open_orders":
        call = service.open_orders(
            {"symbol": symbol, "include_conditional": include_conditional}
        )
    elif action == "create_order":
        call = service.create_order(
            {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": amount,
                "price": price,
                "stop_price": stop_price,
                "callback_rate": callback_rate,
                "activation_price": activation_price,
                "reduce_only": reduce_only,
                "close_position": close_position,
                "position_side": position_side,
                "working_type": working_type,
                "dry_run": dry_run,
            }
        )
    elif action == "cancel_order":
        call = service.cancel_order(
            {"order_id": order_id, "symbol": symbol, "dry_run": dry_run}
        )
    elif action == "set_leverage":
        call = service.set_leverage(
            {"leverage": leverage, "symbol": symbol, "dry_run": dry_run}
        )
    elif action == "set_margin_mode":
        call = service.set_margin_mode(
            {"margin_mode": margin_mode, "symbol": symbol, "dry_run": dry_run}
        )
    else:
        call = service.set_position_mode({"hedge": hedge, "dry_run": dry_run})

    result = run_service(call, output=output)
    echo_service_result(result, "binance-perp", output)
