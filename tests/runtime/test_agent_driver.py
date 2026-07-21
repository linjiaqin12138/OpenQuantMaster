import asyncio
import sys
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from runtime.agent_gateway.agent_driver import AgentDriver
from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.agent_gateway.backends.cli_backend import CliBackend
from runtime.config_loader import AgentConfig


@pytest.mark.unit
def test_agent_driver_selects_cli_backend():
    config = AgentConfig(tool_callback="cli")
    driver = AgentDriver(config)
    assert isinstance(driver._backend, CliBackend)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_command_construction_default_cli(tmp_path):
    config = AgentConfig(
        default_cli="echo",
        headless_args=["--allow-external"],
        tool_callback="cli",
    )
    backend = CliBackend(config)
    task = AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze demo data",
        previous_artifact_path=str(tmp_path / "artifact.json"),
        output_dir=str(tmp_path / "output"),
        pipeline_run_id="run-123",
    )

    (tmp_path / "output").mkdir(parents=True, exist_ok=True)
    (tmp_path / "output" / "report.md").write_text("<!-- summary: ok -->")

    captured_cmd = None

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        nonlocal captured_cmd
        captured_cmd = cmd
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate.return_value = (b"", b"")
        return proc

    with patch.object(asyncio, "create_subprocess_exec", side_effect=fake_create_subprocess_exec):
        result = await backend.run(task)

    assert result.success is True
    assert captured_cmd is not None
    assert captured_cmd[0] == "echo"
    assert "--allow-external" in captured_cmd
    assert "--skill" in captured_cmd
    assert "--artifact" in captured_cmd
    assert "--output-dir" in captured_cmd
    assert "--task" in captured_cmd


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_run_success(tmp_path):
    script_path = tmp_path / "fake_agent.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import argparse
            import pathlib

            parser = argparse.ArgumentParser()
            parser.add_argument("--skill")
            parser.add_argument("--artifact")
            parser.add_argument("--output-dir")
            parser.add_argument("--task")
            args = parser.parse_args()

            output_dir = pathlib.Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "report.md").write_text(
                "Analysis complete.\\n<!-- summary: The demo signals are bullish. -->\\n"
            )
            """
        )
    )

    config = AgentConfig(
        default_cli=sys.executable,
        headless_args=[str(script_path)],
        tool_callback="cli",
    )
    backend = CliBackend(config)
    task = AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze the generated data and write a short report.",
        previous_artifact_path=str(tmp_path / "demo_data.json"),
        output_dir=str(tmp_path / "agent_analyze"),
        pipeline_run_id="run-123",
    )

    result = await backend.run(task)

    assert isinstance(result, AgentResult)
    assert result.success is True
    assert result.report_artifact == "report.md"
    assert result.summary == "The demo signals are bullish."


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_run_missing_report(tmp_path):
    script_path = tmp_path / "fake_agent_no_report.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import argparse
            parser = argparse.ArgumentParser()
            parser.add_argument("--skill")
            parser.add_argument("--artifact")
            parser.add_argument("--output-dir")
            parser.add_argument("--task")
            args = parser.parse_args()
            """
        )
    )

    config = AgentConfig(
        default_cli=sys.executable,
        headless_args=[str(script_path)],
        tool_callback="cli",
    )
    backend = CliBackend(config)
    task = AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze",
        previous_artifact_path=str(tmp_path / "demo_data.json"),
        output_dir=str(tmp_path / "agent_analyze"),
        pipeline_run_id="run-123",
    )

    result = await backend.run(task)

    assert result.success is False
    assert "Report not found" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_run_timeout(tmp_path):
    script_path = tmp_path / "fake_agent_sleep.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import time
            time.sleep(10)
            """
        )
    )

    config = AgentConfig(
        default_cli=sys.executable,
        headless_args=[str(script_path)],
        tool_callback="cli",
    )
    backend = CliBackend(config)
    task = AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze",
        previous_artifact_path=str(tmp_path / "demo_data.json"),
        output_dir=str(tmp_path / "agent_analyze"),
        pipeline_run_id="run-123",
        timeout_sec=1,
    )

    result = await backend.run(task)

    assert result.success is False
    assert "timed out" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cli_backend_run_nonzero_exit(tmp_path):
    script_path = tmp_path / "fake_agent_fail.py"
    script_path.write_text(
        textwrap.dedent(
            """
            import sys
            print("something went wrong", file=sys.stderr)
            sys.exit(1)
            """
        )
    )

    config = AgentConfig(
        default_cli=sys.executable,
        headless_args=[str(script_path)],
        tool_callback="cli",
    )
    backend = CliBackend(config)
    task = AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze",
        previous_artifact_path=str(tmp_path / "demo_data.json"),
        output_dir=str(tmp_path / "agent_analyze"),
        pipeline_run_id="run-123",
    )

    result = await backend.run(task)

    assert result.success is False
    assert "something went wrong" in result.error
