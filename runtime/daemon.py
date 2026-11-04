from __future__ import annotations

import asyncio
import signal
import uuid
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import click
import structlog

from runtime.bootstrap import StartupError, bootstrap
from runtime.config_loader import load_config
from runtime.logging_config import configure_logging
from runtime.services.pipeline_service import PipelineService

logger = structlog.get_logger()


class Daemon:
    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._app = None

    async def run(
        self,
        config_path: Path | None,
        run_pipeline: str | None,
        preflight: bool,
        package: ModuleType,
        on_message: Callable[[str], None] | None = None,
    ) -> int:
        def emit(message: str) -> None:
            if on_message is not None:
                on_message(message)

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._request_shutdown)

        try:
            self._app = await bootstrap(config_path, package=package)
        except StartupError as exc:
            logger.error("startup.failed", error=str(exc))
            return 1

        logger.info(
            "daemon.started",
            environment=self._app.config.environment,
            tools=self._app.registry.list_tools(),
        )

        if preflight:
            emit("Preflight checks passed.")
            await self._shutdown()
            return 0

        if run_pipeline:
            pipeline_service = PipelineService(
                scheduler=self._app.scheduler,
                store=self._app.store,
            )
            result = await pipeline_service.run({"pipeline_name": run_pipeline, "wait": True})
            run_id = result.data.get("run_id", "")
            status = result.data.get("status", "unknown")
            emit(f"Started pipeline run: {run_id}")
            emit(f"Pipeline '{run_pipeline}' finished with status: {status}")
            await self._shutdown()
            return 0 if result.success else 1

        emit("Daemon running. Press Ctrl+C to stop.")
        await self._shutdown_event.wait()
        await self._shutdown()
        return 0

    def _request_shutdown(self) -> None:
        logger.info("daemon.shutdown.requested")
        self._shutdown_event.set()

    async def _shutdown(self) -> None:
        if self._app is None:
            return
        await self._app.bus.publish(
            "daemon.shutdown.requested",
            {},
            correlation_id=uuid.uuid4(),
        )
        await self._app.scheduler.stop()
        await self._app.bus.stop()
        await self._app.store.close()
        logger.info("daemon.shutdown.complete")


@click.command()
@click.option("--run", "run_pipeline", help="Run a pipeline immediately and exit.")
@click.option("--config", "config_path", type=click.Path(path_type=Path), help="Path to config.yaml.")
@click.option("--preflight", is_flag=True, help="Check startup health and exit.")
def main(run_pipeline: str | None, config_path: Path | None, preflight: bool) -> None:
    import tools

    cfg = load_config(config_path)
    configure_logging(cfg)
    daemon = Daemon()
    exit_code = asyncio.run(
        daemon.run(
            config_path,
            run_pipeline,
            preflight,
            package=tools,
            on_message=click.echo,
        )
    )
    if exit_code:
        raise click.ClickException(f"Exit code: {exit_code}")


if __name__ == "__main__":
    main()
