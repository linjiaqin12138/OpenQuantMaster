from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from runtime.config_loader import load_config
from runtime.daemon import Daemon
from runtime.logging_config import configure_logging
from runtime.services.echo_service import EchoService
from tools.base.tool_registry import ToolRegistry
from tools.runtime.parallel_tool import ParallelTool

# Transitional CLI aliases: protocol tool names → service constructors.
_SERVICE_BY_PROTOCOL_NAME: dict[str, type] = {
    "echo": EchoService,
    "echo_tool": EchoService,
}


def _build_registry() -> ToolRegistry:
    import tools

    registry = ToolRegistry()
    registry.discover(tools)
    registry.register(ParallelTool(registry=registry))
    return registry


@click.group()
def cli() -> None:
    """OpenQuantMaster runtime CLI."""
    pass


@cli.command()
@click.argument("pipeline_name")
@click.option("--config", "config_path", type=click.Path(path_type=Path), help="Path to config.yaml.")
def run_pipeline(pipeline_name: str, config_path: Path | None) -> None:
    import tools

    cfg = load_config(config_path)
    configure_logging(cfg)
    daemon = Daemon()
    exit_code = asyncio.run(
        daemon.run(
            config_path,
            pipeline_name,
            preflight=False,
            package=tools,
            on_message=click.echo,
        )
    )
    if exit_code:
        raise click.ClickException(f"Pipeline failed with exit code: {exit_code}")


@cli.command()
@click.argument("tool_name")
@click.option("--inputs", default="{}", help="JSON-encoded inputs for the tool.")
@click.option("--config", "config_path", type=click.Path(path_type=Path), help="Path to config.yaml.")
def tool(tool_name: str, inputs: str, config_path: Path | None) -> None:
    cfg = load_config(config_path)
    configure_logging(cfg)
    parsed = json.loads(inputs)

    service_cls = _SERVICE_BY_PROTOCOL_NAME.get(tool_name)
    if service_cls is not None:
        result = asyncio.run(service_cls().run(parsed))
        click.echo(result.model_dump_json())
        if not result.success:
            raise click.ClickException(result.error or "Service failed")
        return

    # Unmigrated tools: transitional registry path (tool shells should delegate to services).
    registry = _build_registry()
    discovered_tool = registry.get(tool_name)
    result = asyncio.run(discovered_tool.execute(parsed))
    click.echo(result.model_dump_json())


@cli.command(name="list-tools")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="json",
    help="Output format.",
)
def list_tools(fmt: str) -> None:
    registry = _build_registry()
    rows = []
    for name in registry.list_tools():
        tool = registry.get(name)
        rows.append(
            {
                "name": tool.name,
                "capability": tool.capability,
                "version": tool.version,
                "input_schema": tool.input_schema,
                "output_schema": tool.output_schema,
            }
        )

    if fmt == "json":
        click.echo(json.dumps(rows, indent=2, ensure_ascii=False))
        return

    lines = ["# OpenQuantMaster registered tools", ""]
    for row in rows:
        lines.append(f"## {row['name']} (v{row['version']}, capability: {row['capability']})")
        lines.append("")
        lines.append("**Input schema**")
        lines.append("```json")
        lines.append(json.dumps(row["input_schema"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
        lines.append("**Output schema**")
        lines.append("```json")
        lines.append(json.dumps(row["output_schema"], indent=2, ensure_ascii=False))
        lines.append("```")
        lines.append("")
    click.echo("\n".join(lines))


if __name__ == "__main__":
    cli()
