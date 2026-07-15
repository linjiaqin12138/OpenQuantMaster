from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler

if TYPE_CHECKING:
    from runtime.pipeline_runner.runner import PipelineRunner


class APSchedulerAdapter:
    def __init__(self, timezone: str = "UTC") -> None:
        self._scheduler = AsyncIOScheduler(timezone=timezone)
        self._runner: PipelineRunner | None = None

    async def start(self) -> None:
        self._scheduler.start()

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=True)

    def register_executor(self, runner: PipelineRunner) -> None:
        self._runner = runner

    async def run_now(self, pipeline_name: str, inputs: dict[str, Any] | None = None) -> uuid.UUID:
        if self._runner is None:
            raise RuntimeError("No runner registered with scheduler")
        run_id = uuid.uuid4()
        self._scheduler.add_job(
            func=self._runner.run_pipeline,
            args=(pipeline_name,),
            kwargs={"inputs": inputs, "run_id": run_id},
            id=f"manual-{run_id}",
            replace_existing=True,
            next_run_time=datetime.now(timezone.utc),
        )
        return run_id
