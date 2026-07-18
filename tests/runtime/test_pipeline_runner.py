import pytest
import pytest_asyncio
import yaml
from typing import Any, ClassVar
from pydantic import BaseModel

from runtime.bootstrap import bootstrap
from runtime.state_store.models import MarketType, RunStatus, SignalSide
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult
from tools.demo.echo_tool import EchoInput, EchoOutput


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


class ContentEchoTool(BaseTool):
    name: ClassVar[str] = "content_echo_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "demo"
    input_model: ClassVar[type[BaseModel]] = EchoInput
    output_model: ClassVar[type[BaseModel]] = EchoOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={"echoed": inputs["message"]},
            artifacts=[
                ArtifactRef(
                    name="echo.txt",
                    mime_type="text/plain",
                    relative_path="run/stage/echo.txt",
                    sha256="a" * 64,
                    content="hello world",
                )
            ],
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runner_writes_artifact_content(runner_setup):
    registry = runner_setup.registry
    registry._tools["content_echo_tool"] = ContentEchoTool()
    pipelines_dir = runner_setup.runner._pipelines_dir
    (pipelines_dir / "content_pipeline.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "content_pipeline",
                "version": "1.0",
                "stages": [
                    {"name": "echo", "tool": "content_echo_tool", "inputs": {"message": "hi"}},
                ],
            }
        )
    )
    run_id = await runner_setup.runner.run_pipeline("content_pipeline")
    run = await runner_setup.store.get_pipeline_run(run_id)
    assert run.status == RunStatus.completed
    artifact_path = runner_setup.config.paths.artifacts / str(run_id) / "echo" / "echo.txt"
    assert artifact_path.read_text() == "hello world"


class SignalInput(BaseModel):
    message: str


class SignalOutput(BaseModel):
    signals: list[dict[str, Any]]


class SignalEmitTool(BaseTool):
    name: ClassVar[str] = "signal_emit_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "demo"
    input_model: ClassVar[type[BaseModel]] = SignalInput
    output_model: ClassVar[type[BaseModel]] = SignalOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=True,
            data={
                "signals": [
                    {
                        "source": "test",
                        "strategy_id": "dual_ema_v1",
                        "symbol": "BTCUSDT",
                        "market": "crypto",
                        "side": "long",
                        "strength": 0.9,
                        "generated_at": "2026-07-16T08:00:00Z",
                        "metadata": {"reason": "test"},
                    }
                ]
            },
            artifacts=[
                ArtifactRef(
                    name="signals.json",
                    mime_type="application/json",
                    relative_path="signals.json",
                    sha256="",
                    content="[]",
                )
            ],
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runner_persists_signals_from_tool_output(runner_setup):
    runner_setup.registry._tools["signal_emit_tool"] = SignalEmitTool()
    pipelines_dir = runner_setup.runner._pipelines_dir
    (pipelines_dir / "signal_pipeline.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "signal_pipeline",
                "version": "1.0",
                "stages": [
                    {
                        "name": "emit",
                        "tool": "signal_emit_tool",
                        "inputs": {"message": "go"},
                    }
                ],
            }
        )
    )
    run_id = await runner_setup.runner.run_pipeline("signal_pipeline")
    run = await runner_setup.store.get_pipeline_run(run_id)
    assert run.status == RunStatus.completed
    signals = await runner_setup.store.list_signals("dual_ema_v1")
    assert len(signals) == 1
    assert signals[0].symbol == "BTCUSDT"
    assert signals[0].side == SignalSide.long
    assert signals[0].market == MarketType.crypto
