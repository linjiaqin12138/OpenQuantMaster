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


@click.group(invoke_without_command=True)
@click.option("--config", "config_path", type=click.Path(path_type=Path), help="YAML config file path.")
@click.pass_context
def main(ctx: click.Context, config_path: Path | None) -> None:
    """OpenQuantMaster service command-line interface."""
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


@main.group()
def run() -> None:
    """Run a service."""


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
