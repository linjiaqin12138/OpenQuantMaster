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
