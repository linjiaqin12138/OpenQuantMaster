import sys
import textwrap
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
import yaml

from runtime.bootstrap import bootstrap
from runtime.state_store.models import RunStatus


@pytest_asyncio.fixture
async def agent_demo_setup(tmp_path, monkeypatch):
    import tools

    monkeypatch.chdir(tmp_path)

    artifacts_dir = tmp_path / "artifacts"
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()

    fake_script = tmp_path / "fake_agent_cli.py"
    fake_script.write_text(
        textwrap.dedent(
            """
            import argparse
            import json
            import pathlib

            parser = argparse.ArgumentParser()
            parser.add_argument("--skill")
            parser.add_argument("--artifact")
            parser.add_argument("--output-dir")
            parser.add_argument("--task")
            args = parser.parse_args()

            artifact_path = pathlib.Path(args.artifact)
            data = json.loads(artifact_path.read_text(encoding="utf-8"))

            output_dir = pathlib.Path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "report.md").write_text(
                f"# Analysis\\n\\n"
                f"Topic: {data['topic']}\\n"
                f"Signals: {len(data['data'])} rows\\n\\n"
                f"<!-- summary: The demo signals are bullish. -->\\n"
            )
            """
        )
    )

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: {artifacts_dir}
  logs: {tmp_path / "logs"}
  database: {tmp_path / "data" / "runtime.db"}
scheduler:
  timezone: UTC
event_bus:
  backend: memory
logging:
  level: DEBUG
  format: console
agent:
  default_cli: {sys.executable}
  custom_command: {sys.executable} {fake_script}
  tool_callback: cli
notifier:
  pushplus:
    enabled: true
    token: test-token
"""
    )

    pipelines_dir.joinpath("agent_demo.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "agent_demo",
                "version": "1.0",
                "description": "Agent demo integration test",
                "trigger": {"type": "manual"},
                "stages": [
                    {
                        "name": "generate_data",
                        "tool": "demo_data_tool",
                        "inputs": {"topic": "BTC market outlook"},
                    },
                    {
                        "name": "agent_analyze",
                        "tool": "agent_tool",
                        "inputs": {
                            "skill": "core/agent_demo",
                            "task_description": "Analyze the generated data and write a short report.",
                            "timeout_sec": 120,
                        },
                    },
                    {
                        "name": "notify",
                        "tool": "notify_tool",
                        "inputs": {
                            "subject": "Agent Demo Report",
                            "body": "$agent_analyze.summary",
                            "channels": ["pushplus"],
                        },
                    },
                ],
            }
        )
    )

    with patch(
        "runtime.notifier.pushplus_notifier.PushplusNotifier.send",
        new=AsyncMock(return_value={"pushplus": "ok"}),
    ):
        result = await bootstrap(config_path, package=tools)

    result.config.paths.artifacts = artifacts_dir
    result.runner._pipelines_dir = pipelines_dir

    yield result

    await result.scheduler.stop()
    await result.store.close()
    await result.bus.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_demo_pipeline_end_to_end(agent_demo_setup):
    run_id = await agent_demo_setup.runner.run_pipeline("agent_demo")
    run = await agent_demo_setup.store.get_pipeline_run(run_id)

    assert run.status == RunStatus.completed

    report_path = agent_demo_setup.config.paths.artifacts / str(run_id) / "agent_analyze" / "report.md"
    assert report_path.exists()

    notify_stage = next((s for s in run.stage_runs if s.stage_name == "notify"), None)
    assert notify_stage is not None
    assert notify_stage.inputs_snapshot is not None
    assert notify_stage.inputs_snapshot["body"] == "The demo signals are bullish."
