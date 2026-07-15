import subprocess
import sys

import pytest
import pytest_asyncio

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
    yield result
    await result.scheduler.stop()
    await result.store.close()
    await result.bus.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_wires_all_subsystems(boot):
    assert boot.config.environment == "testing"
    assert boot.store is not None
    assert boot.bus is not None
    assert "echo_tool" in boot.registry.list_tools()
    assert boot.scheduler is not None
    assert boot.runner is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_bootstrap_fails_on_missing_config():
    import tools

    with pytest.raises(StartupError):
        await bootstrap("/nonexistent/config.yaml", package=tools)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduler_run_now_triggers_runner(boot):
    from runtime.pipeline_runner.runner import PipelineRunner

    run_id = await boot.scheduler.run_now("hello_pipeline")
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
