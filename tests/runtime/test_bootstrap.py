import subprocess
import sys

import pytest
import pytest_asyncio
import yaml

from runtime.bootstrap import StartupError, bootstrap


@pytest_asyncio.fixture
async def boot(tmp_path, monkeypatch):
    import tools

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
    yield result, config_path
    await result.scheduler.stop()
    await result.store.close()
    await result.bus.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_wires_all_subsystems(boot):
    result, _config_path = boot
    assert result.config.environment == "testing"
    assert result.store is not None
    assert result.bus is not None
    assert "echo_tool" in result.registry.list_tools()
    assert result.scheduler is not None
    assert result.runner is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_defaults_agent_workdir_to_config_dir(boot):
    result, config_path = boot
    assert result.config.agent.workdir == str(config_path.resolve().parent)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_fails_on_missing_config():
    import tools

    with pytest.raises(StartupError):
        await bootstrap("/nonexistent/config.yaml", package=tools)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_schedules_cron_pipelines(tmp_path, monkeypatch):
    import tools

    monkeypatch.chdir(tmp_path)
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    (pipelines_dir / "cron_test.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "cron_test",
                "version": "1.0",
                "trigger": {"type": "cron", "cron": "0 0 * * *", "timezone": "UTC"},
                "stages": [{"name": "noop", "tool": "echo_tool", "inputs": {"message": "hi"}}],
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
    schedules = await result.scheduler._scheduler.get_schedules()
    assert any(schedule.id == "cron:cron_test" for schedule in schedules)
    await result.scheduler.stop()
    await result.store.close()
    await result.bus.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduler_run_now_triggers_runner(boot):
    result, _config_path = boot
    run_id = await result.scheduler.run_now("hello_pipeline")
    assert run_id is not None


@pytest.mark.integration
def test_cli_preflight():
    result = subprocess.run(
        [sys.executable, "-m", "runtime.daemon", "--preflight"],
        cwd="/home/jqlin/Project/OpenQuantMaster",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "Preflight checks passed" in result.stdout


@pytest.mark.integration
def test_cli_run_hello_pipeline():
    result = subprocess.run(
        [sys.executable, "-m", "runtime.daemon", "--run", "hello_pipeline"],
        cwd="/home/jqlin/Project/OpenQuantMaster",
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "finished with status: completed" in result.stdout
