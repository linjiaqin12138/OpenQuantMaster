from runtime.agent_gateway.adapters.base import (
    STAGE_SYSTEM_PROMPT,
    AdapterCommand,
    agent_env,
    build_prompt,
)
from runtime.agent_gateway.adapters.claude_adapter import ClaudeAdapter
from runtime.agent_gateway.adapters.codex_adapter import CodexAdapter
from runtime.agent_gateway.adapters.generic_adapter import GenericAdapter
from runtime.agent_gateway.adapters.kimi_adapter import KimiAdapter
from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig


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


def test_claude_adapter_composes_command():
    config = AgentConfig(adapter="claude", default_cli="claude", headless_args=["--verbose"])
    cmd = ClaudeAdapter(config).compose_command(_task())
    assert cmd.argv[0] == "claude"
    assert cmd.argv[1] == "--verbose"
    assert "--allowed-tools" in cmd.argv
    assert cmd.argv[cmd.argv.index("--allowed-tools") + 1] == "Read,Write,Edit,Bash,Skill"
    assert "--append-system-prompt" in cmd.argv
    assert cmd.argv[cmd.argv.index("--append-system-prompt") + 1] == STAGE_SYSTEM_PROMPT
    assert cmd.argv[-2] == "-p"
    assert "agent_demo" in cmd.argv[-1]
    assert cmd.env["OQM_OUTPUT_DIR"] == "artifacts/run-1/agent_analyze"


def test_codex_adapter_composes_command():
    config = AgentConfig(adapter="codex", default_cli="codex")
    cmd = CodexAdapter(config).compose_command(_task())
    assert cmd.argv[:5] == [
        "codex",
        "-c",
        "approval_policy=never",
        "-c",
        "sandbox_mode=workspace-write",
    ]
    assert cmd.argv[-2] == "exec"
    assert "agent_demo" in cmd.argv[-1]
    assert "-p" not in cmd.argv  # codex takes a positional prompt


def test_kimi_adapter_composes_command():
    config = AgentConfig(adapter="kimi", default_cli="kimi", headless_args=["--yes"])
    cmd = KimiAdapter(config).compose_command(_task())
    assert cmd.argv[:2] == ["kimi", "--yes"]
    assert cmd.argv[-2] == "-p"
    assert "agent_demo" in cmd.argv[-1]


def test_generic_adapter_uses_configured_prompt_flag():
    config = AgentConfig(
        adapter="generic",
        default_cli="mycli",
        headless_args=["--quiet"],
        generic={"prompt_flag": "--prompt"},
    )
    cmd = GenericAdapter(config).compose_command(_task())
    assert cmd.argv[:2] == ["mycli", "--quiet"]
    assert cmd.argv[-2] == "--prompt"
    assert "agent_demo" in cmd.argv[-1]
