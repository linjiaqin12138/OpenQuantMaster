from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from runtime.agent_gateway.agent_driver import AgentDriver
from runtime.agent_gateway.agent_result import AgentResult
from tools.agent.agent_tool import AgentTool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_tool_propagates_success_result(tmp_path):
    mock_driver = AsyncMock(spec=AgentDriver)
    mock_driver.run.return_value = AgentResult(
        success=True,
        report_artifact="report.md",
        summary="The demo signals are bullish.",
    )

    tool = AgentTool(agent_driver=mock_driver, artifacts_path=tmp_path)
    run_id = "run-123"

    # Pre-create the report the tool reads back
    report_dir = tmp_path / run_id / "agent_analyze"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.joinpath("report.md").write_text(
        "Analysis complete.\n<!-- summary: The demo signals are bullish. -->\n"
    )

    result = await tool.execute(
        {
            "skill": "core/agent_demo",
            "task_description": "Analyze the generated data and write a short report.",
            "pipeline_run_id": run_id,
        }
    )

    assert result.success is True
    assert result.data["report_artifact"] == "report.md"
    assert result.data["summary"] == "The demo signals are bullish."

    assert len(result.artifacts) == 1
    artifact = result.artifacts[0]
    assert artifact.name == "report.md"
    assert artifact.mime_type == "text/markdown"
    assert artifact.content == "Analysis complete.\n<!-- summary: The demo signals are bullish. -->\n"

    call_args = mock_driver.run.call_args
    task = call_args.args[0]
    assert task.skill_path == "core/agent_demo"
    assert task.pipeline_run_id == run_id
    assert Path(task.previous_artifact_path) == tmp_path / run_id / "generate_data" / "demo_data.json"
    assert Path(task.output_dir) == tmp_path / run_id / "agent_analyze"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_tool_uses_driver_default_timeout_when_omitted(tmp_path):
    mock_driver = AsyncMock(spec=AgentDriver)
    mock_driver.default_timeout_sec = 300
    mock_driver.run.return_value = AgentResult(
        success=True,
        report_artifact="report.md",
        summary="done",
    )

    tool = AgentTool(agent_driver=mock_driver, artifacts_path=tmp_path)
    run_id = "run-timeout-default"
    report_dir = tmp_path / run_id / "agent_analyze"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.joinpath("report.md").write_text("Report\n<!-- summary: done -->\n")

    result = await tool.execute(
        {
            "skill": "core/agent_demo",
            "task_description": "Analyze data.",
            "pipeline_run_id": run_id,
        }
    )

    assert result.success is True
    task = mock_driver.run.call_args.args[0]
    assert task.timeout_sec == 300


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_tool_explicit_timeout_wins_over_config_default(tmp_path):
    mock_driver = AsyncMock(spec=AgentDriver)
    mock_driver.default_timeout_sec = 300
    mock_driver.run.return_value = AgentResult(
        success=True,
        report_artifact="report.md",
        summary="done",
    )

    tool = AgentTool(agent_driver=mock_driver, artifacts_path=tmp_path)
    run_id = "run-timeout-explicit"
    report_dir = tmp_path / run_id / "agent_analyze"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.joinpath("report.md").write_text("Report\n<!-- summary: done -->\n")

    result = await tool.execute(
        {
            "skill": "core/agent_demo",
            "task_description": "Analyze data.",
            "pipeline_run_id": run_id,
            "timeout_sec": 42,
        }
    )

    assert result.success is True
    task = mock_driver.run.call_args.args[0]
    assert task.timeout_sec == 42
