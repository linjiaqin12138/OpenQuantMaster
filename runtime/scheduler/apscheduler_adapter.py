from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING, Any

from apscheduler import AsyncScheduler

if TYPE_CHECKING:
    from runtime.pipeline_runner.runner import PipelineRunner


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
            await self._task
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
