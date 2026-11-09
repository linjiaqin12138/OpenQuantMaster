from __future__ import annotations

import asyncio
import json
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click
from jsonpath_ng.exceptions import JSONPathError
from jsonpath_ng.ext import parse
from rich.console import Console

from src.models.result import ServiceResult

RichRenderer = Callable[[dict[str, Any]], None]
_rich_renderers: dict[str, RichRenderer] = {}

# The CLI owns its own external error specification; service error codes are
# mapped here and never exposed unchanged.
_CLI_ERROR_CODES = {
    "invalid_input": "INVALID_INPUT",
    "invalid_output": "INVALID_OUTPUT",
    "unsupported_market": "UNSUPPORTED_MARKET",
    "unsupported_source": "UNSUPPORTED_SOURCE",
    "ambiguous_symbol": "AMBIGUOUS_SYMBOL",
    "market_data_unavailable": "MARKET_DATA_UNAVAILABLE",
    "market_data_rejected": "MARKET_DATA_REJECTED",
    "market_data_failed": "MARKET_DATA_FAILED",
    "unknown_indicator": "UNKNOWN_INDICATOR",
    "insufficient_data": "INSUFFICIENT_DATA",
    "all_sources_failed": "ALL_SOURCES_FAILED",
    "news_source_failed": "NEWS_SOURCE_FAILED",
    "news_source_unavailable": "NEWS_SOURCE_UNAVAILABLE",
    "missing_provider_token": "MISSING_PROVIDER_TOKEN",
    "unsupported_provider": "UNSUPPORTED_PROVIDER",
    "notification_rejected": "NOTIFICATION_REJECTED",
    "notification_unavailable": "NOTIFICATION_UNAVAILABLE",
    "notification_failed": "NOTIFICATION_FAILED",
    "unsupported_action": "UNSUPPORTED_ACTION",
    "order_rejected": "ORDER_REJECTED",
    "exchange_unavailable": "EXCHANGE_UNAVAILABLE",
    "exchange_failed": "EXCHANGE_FAILED",
}

_CLI_FALLBACK_ERROR_CODE = "ACTION_FAILED"
_CLI_INTERNAL_ERROR_CODE = "INTERNAL_ERROR"


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


def register_service(command: click.Command, *, renderer: RichRenderer | None = None) -> None:
    run.add_command(command)
    if renderer is not None:
        _rich_renderers[command.name] = renderer


def run_service(coro: Any, *, output: str = "rich") -> ServiceResult:
    """Run a service call and turn unexpected failures into a CLI error.

    The protocol is the last boundary for uncaught exceptions, so an
    unexpected failure is reported as an internal CLI error with its stack
    trace instead of a raw traceback.
    """
    try:
        return asyncio.run(coro)
    except Exception as exc:
        _echo_internal_error(exc, output=output)
        raise click.exceptions.Exit(1) from exc


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
    code = _CLI_ERROR_CODES.get(error.code, _CLI_FALLBACK_ERROR_CODE)
    if output == "rich":
        Console(stderr=True).print(f"[bold red]{code}[/bold red]: {error.message}")
        if error.exception is not None:
            Console(stderr=True).print(
                "".join(traceback.format_exception(error.exception)).rstrip()
            )
    else:
        _echo_json(
            {
                "error": {
                    "code": code,
                    "message": error.message,
                }
            },
            error=True,
        )


def _echo_internal_error(exc: Exception, *, output: str) -> None:
    if output == "rich":
        Console(stderr=True).print(f"[bold red]{_CLI_INTERNAL_ERROR_CODE}[/bold red]: {exc}")
        Console(stderr=True).print("".join(traceback.format_exception(exc)).rstrip())
    else:
        _echo_json(
            {
                "error": {
                    "code": _CLI_INTERNAL_ERROR_CODE,
                    "message": str(exc),
                }
            },
            error=True,
        )


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
