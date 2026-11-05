from __future__ import annotations

import asyncio
from typing import Any

import click
from rich.console import Console

from src.config import load_config
from src.entry.cli.base import echo_service_result, output_option
from src.services.notification import NotificationService


def render_notification(data: dict[str, Any]) -> None:
    Console().print(
        f"[bold green]Notification sent[/bold green] via {data['provider']} "
        f"[dim](format={data['format']}, message_id={data['message_id'] or '-'})[/dim]"
    )


@click.command(
    epilog="""
\b
Examples:
  qm-cli run notification --title "Order filled" --content "BTCUSDT filled"
  qm-cli run notification --content "**Backup completed**" --format markdown -o json
""",
)
@click.option("--title", default="", help="Notification title.")
@click.option("--content", required=True, help="Notification body.")
@click.option(
    "--format",
    "content_format",
    default="html",
    show_default=True,
    type=click.Choice(["html", "txt", "markdown", "json"]),
    help="Notification content format.",
)
@output_option
@click.pass_context
def notification(ctx: click.Context, title: str, content: str, content_format: str, output: str) -> None:
    """Send a notification through the configured provider."""
    try:
        config = load_config(ctx.obj["config_path"])
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
    result = asyncio.run(
        NotificationService.from_config(config).run(
            {"title": title, "content": content, "format": content_format}
        )
    )
    echo_service_result(result, "notification", output)
