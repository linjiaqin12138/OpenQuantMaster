from __future__ import annotations

import asyncio
from pathlib import Path

import click

from runtime.daemon import Daemon


@click.command()
@click.argument("pipeline_name")
@click.option("--config", "config_path", type=click.Path(path_type=Path), help="Path to config.yaml.")
def run_pipeline(pipeline_name: str, config_path: Path | None) -> None:
    import tools

    daemon = Daemon()
    exit_code = asyncio.run(daemon.run(config_path, pipeline_name, preflight=False, package=tools))
    if exit_code:
        raise click.ClickException(f"Pipeline failed with exit code: {exit_code}")
