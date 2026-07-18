import asyncio
from pathlib import Path

import pytest
import pytest_asyncio
import yaml

from runtime.scheduler.apscheduler_adapter import APSchedulerAdapter


@pytest_asyncio.fixture
async def scheduler():
    s = APSchedulerAdapter(timezone="UTC")
    await s.start()
    yield s
    await s.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_schedule_pipelines_loads_cron_job(tmp_path, scheduler):
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    (pipelines_dir / "test_cron.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "test_cron",
                "version": "1.0",
                "trigger": {"type": "cron", "cron": "*/5 * * * *", "timezone": "UTC"},
                "stages": [],
            }
        )
    )

    class FakeRunner:
        def __init__(self) -> None:
            self.calls = []

        async def run_pipeline(self, name: str, inputs: dict = None, run_id=None):
            self.calls.append(name)

    runner = FakeRunner()
    scheduler.register_executor(runner)
    await scheduler.schedule_pipelines(pipelines_dir)

    schedules = await scheduler._scheduler.get_schedules()
    assert len(schedules) == 1
    assert schedules[0].id == "cron:test_cron"
