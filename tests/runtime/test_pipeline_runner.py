import pytest
import pytest_asyncio
import yaml

from runtime.bootstrap import bootstrap
from runtime.state_store.models import RunStatus


@pytest_asyncio.fixture
async def runner_setup(tmp_path, monkeypatch):
    import tools

    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    (pipelines_dir / "hello_pipeline.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "hello_pipeline",
                "version": "1.0",
                "stages": [
                    {"name": "greet", "tool": "echo_tool", "inputs": {"message": "hello", "repeat": 1}},
                    {"name": "repeat", "tool": "echo_tool", "inputs": {"message": "world", "repeat": 2}},
                ],
            }
        )
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: {tmp_path / "artifacts"}
  logs: {tmp_path / "logs"}
  database: {tmp_path / "data" / "runtime.db"}
scheduler:
  timezone: UTC
event_bus:
  backend: memory
logging:
  level: DEBUG
  format: console
"""
    )
    result = await bootstrap(config_path, package=tools)
    # Monkeypatch config paths to point test pipelines directory
    result.config.paths.artifacts = tmp_path / "artifacts"
    result.runner._pipelines_dir = pipelines_dir
    yield result
    await result.store.close()
    await result.bus.stop()
    await result.scheduler.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_pipeline_completes(runner_setup):
    run_id = await runner_setup.runner.run_pipeline("hello_pipeline")
    run = await runner_setup.store.get_pipeline_run(run_id)
    assert run is not None
    assert run.status == RunStatus.completed
    assert len(run.stage_runs) == 2
    assert run.stage_runs[0].status == RunStatus.completed
    assert run.stage_runs[1].outputs_snapshot["data"]["echoed"] == "world world"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_run_pipeline_fails_for_unknown_tool(runner_setup):
    pipelines_dir = runner_setup.runner._pipelines_dir
    (pipelines_dir / "bad_pipeline.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "bad_pipeline",
                "version": "1.0",
                "stages": [
                    {"name": "fail", "tool": "missing_tool", "inputs": {}},
                ],
            }
        )
    )
    run_id = await runner_setup.runner.run_pipeline("bad_pipeline")
    run = await runner_setup.store.get_pipeline_run(run_id)
    assert run.status == RunStatus.failed
