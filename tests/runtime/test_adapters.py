from runtime.agent_gateway.adapters.base import AdapterCommand, agent_env, build_prompt
from runtime.agent_gateway.agent_task import AgentTask


def _task() -> AgentTask:
    return AgentTask(
        skill_path="core/agent_demo",
        task_description="Analyze the generated data and write a short report.",
        previous_artifact_path="artifacts/run-1/generate_data/demo_data.json",
        output_dir="artifacts/run-1/agent_analyze",
        pipeline_run_id="run-1",
    )


def test_agent_env():
    env = agent_env(_task())
    assert env == {
        "OQM_RUN_ID": "run-1",
        "OQM_OUTPUT_DIR": "artifacts/run-1/agent_analyze",
    }


def test_build_prompt_references_skill_artifact_and_output():
    prompt = build_prompt(_task())
    assert "agent_demo" in prompt
    assert "artifacts/run-1/generate_data/demo_data.json" in prompt
    assert "Analyze the generated data and write a short report." in prompt
    assert "$OQM_OUTPUT_DIR/report.md" in prompt
    assert "<!-- summary:" in prompt
    # skill/artifact contents must NOT be embedded
    assert "momentum" not in prompt


def test_adapter_command_defaults_cwd_none():
    cmd = AdapterCommand(argv=["echo", "hi"], env={})
    assert cmd.cwd is None
