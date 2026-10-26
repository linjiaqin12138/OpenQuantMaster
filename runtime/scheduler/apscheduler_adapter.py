from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml
from apscheduler import AsyncScheduler
from apscheduler._enums import ConflictPolicy
from apscheduler.triggers.cron import CronTrigger

if TYPE_CHECKING:
    from runtime.pipeline_runner.runner import PipelineRunner

logger = structlog.get_logger()


def _parse_cron(cron: str) -> dict[str, Any]:
    """Map a 5-field cron string to APScheduler CronTrigger kwargs."""
    parts = cron.split()
    if len(parts) != 5:
        raise ValueError(f"Invalid cron expression (expected 5 fields): {cron}")
    minute, hour, day, month, day_of_week = parts
    return {
        "minute": minute,
        "hour": hour,
        "day": day,
        "month": month,
        "day_of_week": day_of_week,
    }


async def _cron_executor(
    runner: PipelineRunner,
    name: str,
    inputs: dict[str, Any] | None,
) -> None:
    """Module-level wrapper so APScheduler can reference the callable.

    Generates a fresh ``run_id`` for every cron firing to avoid primary-key
    collisions when the schedule is created once but executed repeatedly.
    """
    await runner.run_pipeline(name, inputs=inputs, run_id=uuid.uuid4())


class APSchedulerAdapter:
    def __init__(self, timezone: str = "UTC") -> None:
        self._timezone = timezone
        self._scheduler: AsyncScheduler | None = None
        self._runner: PipelineRunner | None = None
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        started = asyncio.Event()

        async def _run_scheduler() -> None:
            async with AsyncScheduler() as scheduler:
                self._scheduler = scheduler
                await scheduler.start_in_background()
                started.set()
                await self._stop_event.wait()

        self._task = asyncio.create_task(_run_scheduler())
        await started.wait()

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (TimeoutError, asyncio.CancelledError):
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
        self._scheduler = None

    def register_executor(self, runner: PipelineRunner) -> None:
        self._runner = runner

    async def run_now(self, pipeline_name: str, inputs: dict[str, Any] | None = None) -> uuid.UUID:
        if self._runner is None:
            raise RuntimeError("No runner registered with scheduler")
        if self._scheduler is None:
            raise RuntimeError("Scheduler has not been started")
        run_id = uuid.uuid4()
        await self._scheduler.add_job(
            self._runner.run_pipeline,
            args=(pipeline_name,),
            kwargs={"inputs": inputs, "run_id": run_id},
        )
        return run_id

    async def schedule_pipelines(self, pipelines_dir: Path) -> None:
        if self._runner is None:
            raise RuntimeError("No runner registered with scheduler")
        if self._scheduler is None:
            raise RuntimeError("Scheduler has not been started")
        await self._scheduler.configure_task(_cron_executor, max_running_jobs=1)
        for manifest_path in pipelines_dir.glob("*.yaml"):
            try:
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            except Exception as exc:
                logger.warning(
                    "scheduler.manifest_parse_failed",
                    path=str(manifest_path),
                    error=str(exc),
                )
                continue
            trigger = manifest.get("trigger", {})
            if trigger.get("type") != "cron":
                continue
            cron_expr = trigger["cron"]
            tz = trigger.get("timezone", self._timezone)
            await self._scheduler.add_schedule(
                _cron_executor,
                CronTrigger(**_parse_cron(cron_expr), timezone=tz),
                id=f"cron:{manifest['name']}",
                args=(self._runner, manifest["name"]),
                kwargs={"inputs": manifest.get("inputs", {})},
                conflict_policy=ConflictPolicy.replace,
            )
