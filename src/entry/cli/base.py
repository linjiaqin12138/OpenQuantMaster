from __future__ import annotations

import json

import click

from src.services.base import ServiceResult


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """OpenQuantMaster service command-line interface."""
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


def register_cli(command: click.Command) -> click.Command:
    run.add_command(command)
    return command


def echo_service_result(result: ServiceResult) -> None:
    error = None
    if result.error is not None:
        error = {"code": result.error.code, "message": result.error.message}
    click.echo(
        json.dumps(
            {
                "success": result.success,
                "data": result.data,
                "error": error,
                "duration_seconds": result.duration_seconds,
            },
            ensure_ascii=False,
        )
    )
    if not result.success:
        raise click.exceptions.Exit(1)
