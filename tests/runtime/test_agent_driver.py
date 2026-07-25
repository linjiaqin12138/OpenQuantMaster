import asyncio
import sys
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from runtime.agent_gateway.adapters.base import AdapterCommand, BaseAdapter
from runtime.agent_gateway.adapters.claude_adapter import ClaudeAdapter
from runtime.agent_gateway.adapters.codex_adapter import CodexAdapter
from runtime.agent_gateway.adapters.generic_adapter import GenericAdapter
from runtime.agent_gateway.adapters.kimi_adapter import KimiAdapter
from runtime.agent_gateway.agent_driver import AgentDriver
from runtime.agent_gateway.agent_task import AgentTask
from runtime.agent_gateway.backends.cli_backend import CliBackend
from runtime.config_loader import AgentConfig


class FakeAdapter(BaseAdapter):
    def __init__(self, argv: list[str], cwd: str | None = None) -> None:
        self._argv = argv
        self._cwd = cwd

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        return AdapterCommand(
            argv=self._argv,
            env={"OQM_RUN_ID": task.pipeline_run_id, "OQM_OUTPUT_DIR": task.output_dir},
            cwd=self._cwd,
        )


def _task(tmp_path) -> AgentTask:
    return AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze demo data",
        previous_artifact_path=str(tmp_path / "artifact.json"),
        output_dir=str(tmp_path / "output"),
        pipeline_run_id="run-123",
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_uses_adapter_command_and_env(tmp_path):
    config = AgentConfig()
    backend = CliBackend(config, FakeAdapter(["echo", "hello"]))
    task = _task(tmp_path)

    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "report.md").write_text("<!-- summary: ok -->")

    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cmd"] = cmd
        captured["env"] = kwargs.get("env")
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b"", b"")
        return proc

    with patch.object(asyncio, "create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        result = await backend.run(task)

    assert result.success is True
    assert captured["cmd"] == ("echo", "hello")
    assert captured["env"]["OQM_RUN_ID"] == "run-123"
    assert captured["env"]["OQM_OUTPUT_DIR"] == str(tmp_path / "output")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_stdout_fallback_writes_report(tmp_path):
    script = tmp_path / "fake_cli.py"
    script.write_text(
        textwrap.dedent(
            """
            print("# Report from stdout")
            print()
            print("<!-- summary: stdout fallback works. -->")
            """
        )
    )
    config = AgentConfig()
    backend = CliBackend(config, FakeAdapter([sys.executable, str(script)]))

    result = await backend.run(_task(tmp_path))

    assert result.success is True
    assert result.summary == "stdout fallback works."
    report = tmp_path / "output" / "report.md"
    assert report.exists()
    assert "Report from stdout" in report.read_text()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_fails_when_no_report_and_empty_stdout(tmp_path):
    config = AgentConfig()
    backend = CliBackend(config, FakeAdapter([sys.executable, "-c", "pass"]))

    result = await backend.run(_task(tmp_path))

    assert result.success is False
    assert "Report not found" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_cli_not_found(tmp_path):
    config = AgentConfig()
    backend = CliBackend(config, FakeAdapter(["definitely-not-a-real-cli-oqm"]))

    result = await backend.run(_task(tmp_path))

    assert result.success is False
    assert "Agent CLI not found" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_nonzero_exit_returns_stderr(tmp_path):
    config = AgentConfig()
    backend = CliBackend(
        config,
        FakeAdapter([sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]),
    )

    result = await backend.run(_task(tmp_path))

    assert result.success is False
    assert result.error == "boom"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_uses_config_workdir_when_adapter_cwd_is_none(tmp_path):
    config = AgentConfig(workdir="/some/root")
    backend = CliBackend(config, FakeAdapter(["echo", "hello"], cwd=None))
    task = _task(tmp_path)

    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "report.md").write_text("<!-- summary: ok -->")

    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b"", b"")
        return proc

    with patch.object(asyncio, "create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        result = await backend.run(task)

    assert result.success is True
    assert captured["cwd"] == "/some/root"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_adapter_cwd_wins_over_config_workdir(tmp_path):
    config = AgentConfig(workdir="/some/root")
    backend = CliBackend(config, FakeAdapter(["echo", "hello"], cwd="/adapter/root"))
    task = _task(tmp_path)

    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "report.md").write_text("<!-- summary: ok -->")

    captured = {}

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        captured["cwd"] = kwargs.get("cwd")
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b"", b"")
        return proc

    with patch.object(asyncio, "create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        result = await backend.run(task)

    assert result.success is True
    assert captured["cwd"] == "/adapter/root"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_nonzero_exit_tolerates_non_utf8_stderr(tmp_path):
    config = AgentConfig()
    backend = CliBackend(
        config,
        FakeAdapter(
            [sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'\\xff\\xfe bad'); sys.exit(3)"]
        ),
    )

    result = await backend.run(_task(tmp_path))

    assert result.success is False
    assert "bad" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_timeout_kills_process(tmp_path):
    config = AgentConfig()
    backend = CliBackend(
        config,
        FakeAdapter([sys.executable, "-c", "import time; time.sleep(30)"]),
    )
    task = _task(tmp_path)
    task = task.model_copy(update={"timeout_sec": 1})

    result = await backend.run(task)

    assert result.success is False
    assert "timed out" in result.error


@pytest.mark.unit
@pytest.mark.parametrize(
    ("adapter", "expected_cls"),
    [
        ("claude", ClaudeAdapter),
        ("codex", CodexAdapter),
        ("kimi", KimiAdapter),
        ("generic", GenericAdapter),
    ],
)
def test_agent_driver_selects_adapter(adapter, expected_cls):
    driver = AgentDriver(AgentConfig(adapter=adapter))
    assert isinstance(driver._backend, CliBackend)
    assert isinstance(driver._backend._adapter, expected_cls)


@pytest.mark.unit
def test_agent_driver_exposes_default_timeout_sec():
    driver = AgentDriver(AgentConfig(timeout_sec=300))
    assert driver.default_timeout_sec == 300
