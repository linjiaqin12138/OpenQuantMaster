from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from jsonpath_ng.exceptions import JSONPathError
from jsonpath_ng.ext import parse
from rich.console import Console

from src.services.base import ServiceResult

RichRenderer = Callable[[dict[str, Any]], None]
_rich_renderers: dict[str, RichRenderer] = {}


@click.group(
    invoke_without_command=True,
    epilog="""
\b
Examples:
  qm-cli list
  qm-cli run ohlcv --help
  qm-cli run ohlcv --symbol BTCUSDT --market crypto --interval 1h --limit 30
  qm-cli run indicator --symbol BTCUSDT --indicators sma,rsi,macd
  qm-cli run binance-perp balance
  qm-cli --config ~/.qm/config.yaml run ohlcv --symbol AAPL --market us_equity --interval 1d

Use 'qm-cli run SERVICE --help' for service-specific arguments and output options.
""",
)
@click.option(
    "--config",
    "config_path",
    type=click.Path(path_type=Path),
    help="YAML config file. Default lookup: ./config.yaml, then ~/.qm/config.yaml.",
)
@click.pass_context
def main(ctx: click.Context, config_path: Path | None) -> None:
    """Run OpenQuantMaster services from the command line.

    Services share the provider configuration but expose their own arguments.
    Successful commands default to a human-readable rich view. Every service
    also supports JSON output and JSONPath selection through '-o/--output'.
    Failed commands print an error to stderr and return a non-zero exit code.
    """
    ctx.obj = {"config_path": config_path}
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command(name="help")
@click.pass_context
def help_command(ctx: click.Context) -> None:
    """Show this help message."""
    click.echo(ctx.parent.get_help() if ctx.parent else ctx.get_help())


@main.command(name="list")
def list_services() -> None:
    """List available services."""
    for name, command in sorted(run.commands.items()):
        click.echo(f"{name}\t{command.get_short_help_str()}")


@main.group(epilog="Use 'qm-cli run SERVICE --help' for detailed service usage and examples.")
def run() -> None:
    """Run a service with its own arguments and output format."""


output_option = click.option(
    "--output",
    "-o",
    default="rich",
    show_default=True,
    help="Output: rich table, raw data JSON, or jsonpath={.field} applied to data.",
)


def register_cli(*, renderer: RichRenderer | None = None) -> Callable[[click.Command], click.Command]:
    def register(command: click.Command) -> click.Command:
        run.add_command(command)
        if renderer is not None:
            _rich_renderers[command.name] = renderer
        return command

    return register


def echo_service_result(result: ServiceResult, service_name: str, output: str) -> None:
    if not result.success:
        _echo_error(result, output)
        raise click.exceptions.Exit(1)

    if output == "json":
        _echo_json(result.data)
        return
    if output == "rich":
        renderer = _rich_renderers.get(service_name)
        if renderer is None:
            _echo_json(result.data)
        else:
            renderer(result.data)
        return
    if output.startswith("jsonpath="):
        _echo_json(_evaluate_jsonpath(result.data, output.removeprefix("jsonpath=")))
        return
    raise click.ClickException(f"Unsupported output format: {output}")


def _echo_json(data: Any, *, error: bool = False) -> None:
    click.echo(json.dumps(data, ensure_ascii=False), err=error)


def _echo_error(result: ServiceResult, output: str) -> None:
    error = result.error
    if output == "rich":
        Console(stderr=True).print(f"[bold red]{error.code}[/bold red]: {error.message}")
    else:
        _echo_json({"error": {"code": error.code, "message": error.message}}, error=True)


def _evaluate_jsonpath(data: dict[str, Any], expression: str) -> Any:
    normalized = expression.strip()
    if normalized.startswith("{") and normalized.endswith("}"):
        normalized = normalized[1:-1]
    if normalized.startswith("."):
        normalized = f"${normalized}"
    try:
        matches = parse(normalized).find(data)
    except (JSONPathError, ValueError) as exc:
        raise click.ClickException(f"Invalid JSONPath expression: {expression}") from exc
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0].value
    return [match.value for match in matches]
