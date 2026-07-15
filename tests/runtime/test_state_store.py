import uuid
from pathlib import Path

import pytest
import pytest_asyncio

from runtime.state_store.database import StateStore
from runtime.state_store.models import PipelineRun, RunStatus, TriggerType


@pytest.mark.unit
def test_pipeline_run_defaults():
    run = PipelineRun(pipeline_name="hello_pipeline")
    assert run.pipeline_name == "hello_pipeline"
    assert run.status == RunStatus.running
    assert run.trigger_type == TriggerType.manual
    assert run.artifacts_index == {}


@pytest_asyncio.fixture
async def store(tmp_path):
    db_path = tmp_path / "test.db"
    s = StateStore(database_url=f"sqlite+aiosqlite:///{db_path}", artifacts_path=tmp_path / "artifacts")
    await s.init()
    yield s
    await s.close()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_pipeline_run(store):
    run = await store.create_pipeline_run(pipeline_name="hello_pipeline", trigger_type=TriggerType.manual)
    assert run.pipeline_name == "hello_pipeline"
    assert run.status == RunStatus.running
    fetched = await store.get_pipeline_run(run.id)
    assert fetched is not None
    assert fetched.id == run.id


@pytest.mark.unit
@pytest.mark.asyncio
async def test_create_stage_run_and_artifact(store):
    run = await store.create_pipeline_run(pipeline_name="hello_pipeline", trigger_type=TriggerType.manual)
    stage = await store.create_stage_run(
        pipeline_run_id=run.id,
        stage_name="greet",
        sequence=0,
        inputs_snapshot={"message": "hi"},
    )
    assert stage.sequence == 0
    artifact = await store.create_artifact_ref(
        pipeline_run_id=run.id,
        stage_run_id=stage.id,
        name="echo.txt",
        mime_type="text/plain",
        relative_path=f"{run.id}/greet/echo.txt",
        sha256="a" * 64,
    )
    assert artifact.name == "echo.txt"
