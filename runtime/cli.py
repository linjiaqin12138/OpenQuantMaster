from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from runtime.daemon import Daemon
from tools.base.tool_registry import ToolRegistry


@click.group()
def cli() -> None:
    """OpenQuantMaster runtime CLI."""
    pass


@cli.command()
@click.argument("pipeline_name")
@click.option("--config", "config_path", type=click.Path(path_type=Path), help="Path to config.yaml.")
def run_pipeline(pipeline_name: str, config_path: Path | None) -> None:
    import tools

    daemon = Daemon()
    exit_code = asyncio.run(daemon.run(config_path, pipeline_name, preflight=False, package=tools))
    if exit_code:
        raise click.ClickException(f"Pipeline failed with exit code: {exit_code}")


@cli.command()
@click.argument("tool_name")
@click.option("--inputs", default="{}", help="JSON-encoded inputs for the tool.")
def tool(tool_name: str, inputs: str) -> None:
    import tools

    registry = ToolRegistry()
    registry.discover(tools)
    discovered_tool = registry.get(tool_name)
    parsed = json.loads(inputs)
    result = asyncio.run(discovered_tool.execute(parsed))
    click.echo(result.model_dump_json())


if __name__ == "__main__":
    cli()
