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


@cli.command(name="list-tools")
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["json", "markdown"]),
    default="json",
    help="Output format.",
)
def list_tools(fmt: str) -> None:
    import tools

    registry = ToolRegistry()
    registry.discover(tools)
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


@cli.command(name="init-workspace")
@click.option(
    "--agent",
    "agents",
    multiple=True,
    required=True,
    type=click.Choice(["claude", "codex", "kimi"]),
    help="Target agent CLI. Repeatable.",
)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option(
    "--root",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("."),
    help="Project root to initialize.",
)
def init_workspace(agents: tuple[str, ...], force: bool, root: Path) -> None:
    from runtime.workspace.init_workspace import init_workspace as _init

    written = _init(root, list(agents), force=force)
    if not written:
        click.echo("Nothing to write (all files exist; use --force to overwrite).")
    for path in written:
        click.echo(f"wrote {path}")


if __name__ == "__main__":
    cli()
