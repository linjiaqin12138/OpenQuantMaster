from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import structlog

from runtime.config_loader import RuntimeConfig, load_config
from runtime.event_bus.memory_bus import MemoryEventBus
from runtime.notifier.composite import CompositeNotifier, build_notifier
from runtime.pipeline_runner.runner import PipelineRunner
from runtime.scheduler.apscheduler_adapter import APSchedulerAdapter
from runtime.state_store.database import StateStore
from tools.base.tool_registry import ToolRegistry
from tools.notifier.notify_tool import NotifyTool
from tools.runtime.parallel_tool import ParallelTool

logger = structlog.get_logger()


class StartupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class BootstrapResult:
    config: RuntimeConfig
    store: StateStore
    bus: MemoryEventBus
    registry: ToolRegistry
    scheduler: APSchedulerAdapter
    runner: PipelineRunner
    notifier: CompositeNotifier


async def bootstrap(config_path: Path | str | None = None, package: ModuleType | None = None) -> BootstrapResult:
    """Startup order: config -> store -> bus -> registry -> scheduler -> runner."""
    try:
        config = load_config(config_path)
    except Exception as exc:
        raise StartupError(f"Failed to load configuration: {exc}") from exc

    try:
        store = StateStore(database_url=config.database_url, artifacts_path=config.paths.artifacts)
        await store.init()
    except Exception as exc:
        raise StartupError(f"Failed to initialize state store: {exc}") from exc

    try:
        bus = MemoryEventBus()
        await bus.start()
    except Exception as exc:
        await store.close()
        raise StartupError(f"Failed to start event bus: {exc}") from exc

    try:
        registry = ToolRegistry()
        if package is not None:
            discovered = registry.discover(package)
            if discovered == 0:
                raise StartupError("No tools discovered; check tools/ package layout")
    except Exception as exc:
        await bus.stop()
        await store.close()
        raise StartupError(f"Failed to initialize tool registry: {exc}") from exc

    try:
        scheduler = APSchedulerAdapter(timezone=config.scheduler.timezone)
        await scheduler.start()
    except Exception as exc:
        await bus.stop()
        await store.close()
        raise StartupError(f"Failed to start scheduler: {exc}") from exc

    try:
        notifier = build_notifier(config.notifier)
        registry.register(NotifyTool(notifier=notifier))
        registry.register(ParallelTool(registry=registry))
        runner = PipelineRunner(
            config=config,
            store=store,
            bus=bus,
            registry=registry,
            notifier=notifier,
        )
        scheduler.register_executor(runner)
        await scheduler.schedule_pipelines(config.paths.pipelines)
    except Exception as exc:
        await scheduler.stop()
        await bus.stop()
        await store.close()
        raise StartupError(f"Failed to initialize pipeline runner: {exc}") from exc

    logger.info(
        "bootstrap.complete",
        environment=config.environment,
        tools=registry.list_tools(),
        database_url=config.database_url,
    )
    return BootstrapResult(
        config=config,
        store=store,
        bus=bus,
        registry=registry,
        scheduler=scheduler,
        runner=runner,
        notifier=notifier,
    )
