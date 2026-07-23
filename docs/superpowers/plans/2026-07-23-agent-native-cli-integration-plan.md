# Agent Native CLI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flag-based Agent CLI contract with native CLI invocation (adapters per CLI, workspace init, prompt-based headless calls).

**Architecture:** `AgentDriver` selects a per-CLI adapter (`claude`/`codex`/`kimi`/`generic`) that composes native argv with a minimal prompt; `CliBackend` spawns the subprocess with injected env (`OQM_RUN_ID`, `OQM_OUTPUT_DIR`) and recovers `report.md` (stdout fallback). `init-workspace` generates `.claude/` / `.agents/` workspace files with an `oqm-tool` skill and synced business skills. Memory tools are deferred (spec §6).

**Tech Stack:** Python 3.12, pydantic v2, click, pytest/pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-07-23-agent-native-cli-integration-design.md`

## Global Constraints

- No new third-party dependencies.
- `agent_tool` pipeline input/output schema unchanged (`skill`, `task_description`, `timeout_sec` → `success`, `report_artifact`, `summary`).
- Removed config fields: `agent.custom_command`, `agent.tool_callback`, `agent.max_iterations`. New: `agent.adapter`, `agent.generic.prompt_flag`.
- Adapters must use each CLI's plain-text output mode (no JSON/JSONL output flags) so the stdout fallback stays valid.
- Memory tools (`read_memory_tool`/`write_memory_tool`) and `read-memory`/`write-memory` skills are NOT in scope.
- Run tests with `python -m pytest`; lint with `ruff check runtime tools tests`.

---

### Task 1: Reshape `AgentConfig`

**Files:**
- Modify: `runtime/config_loader.py:54-60`
- Modify: `config.yaml` (the `agent:` block, currently ~lines 34-40)
- Test: `tests/runtime/test_config_loader.py`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `GenericAgentConfig(BaseModel)` with field `prompt_flag: str = "-p"`.
  - `AgentConfig(BaseModel)` with fields: `adapter: Literal["claude", "codex", "kimi", "generic"] = "claude"`, `default_cli: str = "claude"`, `timeout_sec: int = 120`, `headless_args: list[str]`, `generic: GenericAgentConfig`. Removed fields: `custom_command`, `tool_callback`, `max_iterations`.

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_config_loader.py`:

```python
def test_agent_config_defaults():
    from runtime.config_loader import AgentConfig

    config = AgentConfig()
    assert config.adapter == "claude"
    assert config.default_cli == "claude"
    assert config.timeout_sec == 120
    assert config.headless_args == []
    assert config.generic.prompt_flag == "-p"


def test_agent_config_generic_adapter():
    from runtime.config_loader import AgentConfig

    config = AgentConfig(adapter="generic", default_cli="mycli", generic={"prompt_flag": "--prompt"})
    assert config.adapter == "generic"
    assert config.generic.prompt_flag == "--prompt"


def test_agent_config_rejects_removed_fields():
    import pytest

    from runtime.config_loader import AgentConfig

    with pytest.raises(ValueError):
        AgentConfig(custom_command="echo hi")
```

(Note: pydantic v2 `BaseModel` forbids extra fields only if configured; check `runtime/config_loader.py` — if models do not set `model_config = ConfigDict(extra="forbid")`, change the last test to assert the field is simply absent: `assert not hasattr(AgentConfig(), "custom_command")` instead of expecting `ValueError`. Pick whichever matches the file's existing convention and keep it consistent.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/runtime/test_config_loader.py -k agent_config -v`
Expected: FAIL (`AgentConfig` has no `adapter` field / still has `custom_command`).

- [ ] **Step 3: Replace the `AgentConfig` class**

In `runtime/config_loader.py`, replace lines 54-60 (the current `AgentConfig`) with:

```python
class GenericAgentConfig(BaseModel):
    prompt_flag: str = "-p"


class AgentConfig(BaseModel):
    adapter: Literal["claude", "codex", "kimi", "generic"] = "claude"
    default_cli: str = "claude"
    timeout_sec: int = 120
    headless_args: list[str] = Field(default_factory=list)
    generic: GenericAgentConfig = Field(default_factory=GenericAgentConfig)
```

(`Literal` and `Field` are already imported in this file — `McpConfig` uses both.)

- [ ] **Step 4: Update `config.yaml`**

Replace the whole `agent:` block with:

```yaml
agent:
  adapter: "claude"
  default_cli: "claude"
  timeout_sec: 300
  headless_args: []
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/runtime/test_config_loader.py -v`
Expected: PASS (including the three new tests). Other test files that reference the removed fields will still fail — that is expected and fixed in Tasks 5, 6, and 9.

- [ ] **Step 6: Commit**

```bash
git add runtime/config_loader.py config.yaml tests/runtime/test_config_loader.py
git commit -m "feat(config): reshape AgentConfig for adapter-based CLI selection"
```

---

### Task 2: Adapter base — `AdapterCommand`, prompt builder, env helper

**Files:**
- Create: `runtime/agent_gateway/adapters/__init__.py` (empty)
- Create: `runtime/agent_gateway/adapters/base.py`
- Test: `tests/runtime/test_adapters.py`

**Interfaces:**
- Consumes: `runtime.agent_gateway.agent_task.AgentTask` (fields: `skill_path: str`, `task_description: str`, `previous_artifact_path: str`, `output_dir: str`, `pipeline_run_id: str`, `timeout_sec: int`).
- Produces:
  - `AdapterCommand` dataclass: `argv: list[str]`, `env: dict[str, str]`, `cwd: str | None = None`.
  - `agent_env(task: AgentTask) -> dict[str, str]` — `{"OQM_RUN_ID": task.pipeline_run_id, "OQM_OUTPUT_DIR": task.output_dir}`.
  - `build_prompt(task: AgentTask) -> str`.
  - `STAGE_SYSTEM_PROMPT: str`.
  - `BaseAdapter(ABC)` with abstract `compose_command(self, task: AgentTask) -> AdapterCommand`.

- [ ] **Step 1: Write the failing test**

Create `tests/runtime/test_adapters.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/runtime/test_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError: runtime.agent_gateway.adapters`.

- [ ] **Step 3: Implement**

Create `runtime/agent_gateway/adapters/__init__.py` (empty file).

Create `runtime/agent_gateway/adapters/base.py`:

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from runtime.agent_gateway.agent_task import AgentTask

STAGE_SYSTEM_PROMPT = (
    "You are running as a stage in an OpenQuantMaster pipeline. "
    "Write your final report to $OQM_OUTPUT_DIR/report.md and end it with "
    "a line: <!-- summary: <one-sentence summary> -->."
)


@dataclass(frozen=True)
class AdapterCommand:
    argv: list[str]
    env: dict[str, str]
    cwd: str | None = None


def agent_env(task: AgentTask) -> dict[str, str]:
    return {
        "OQM_RUN_ID": task.pipeline_run_id,
        "OQM_OUTPUT_DIR": task.output_dir,
    }


def build_prompt(task: AgentTask) -> str:
    skill_name = Path(task.skill_path).stem
    return (
        f"加载 skill '{skill_name}'，阅读上一阶段产物 {task.previous_artifact_path}，"
        f"完成任务：{task.task_description}\n"
        "把最终报告写入 $OQM_OUTPUT_DIR/report.md，"
        "并在末尾加入一行：<!-- summary: 一句话摘要 -->"
    )


class BaseAdapter(ABC):
    @abstractmethod
    def compose_command(self, task: AgentTask) -> AdapterCommand:
        """Build the native argv/env/cwd for one headless Agent invocation."""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/runtime/test_adapters.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add runtime/agent_gateway/adapters/ tests/runtime/test_adapters.py
git commit -m "feat(agent_gateway): add adapter base with prompt builder"
```

---

### Task 3: Claude and Codex adapters

**Files:**
- Create: `runtime/agent_gateway/adapters/claude_adapter.py`
- Create: `runtime/agent_gateway/adapters/codex_adapter.py`
- Test: `tests/runtime/test_adapters.py` (append)

**Interfaces:**
- Consumes: `BaseAdapter`, `AdapterCommand`, `agent_env`, `build_prompt`, `STAGE_SYSTEM_PROMPT` from Task 2; `AgentConfig` from Task 1.
- Produces:
  - `ClaudeAdapter(config: AgentConfig)` → argv `[default_cli, *headless_args, "--allowed-tools", "Read,Write,Edit,Bash,Skill", "--append-system-prompt", STAGE_SYSTEM_PROMPT, "-p", build_prompt(task)]`.
  - `CodexAdapter(config: AgentConfig)` → argv `[default_cli, "-c", "approval_policy=never", "-c", "sandbox_mode=workspace-write", *headless_args, "exec", build_prompt(task)]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_adapters.py`:

```python
from runtime.agent_gateway.adapters.base import STAGE_SYSTEM_PROMPT
from runtime.agent_gateway.adapters.claude_adapter import ClaudeAdapter
from runtime.agent_gateway.adapters.codex_adapter import CodexAdapter
from runtime.config_loader import AgentConfig


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError` for the two adapter modules.

- [ ] **Step 3: Implement**

Create `runtime/agent_gateway/adapters/claude_adapter.py`:

```python
from __future__ import annotations

from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig

from .base import STAGE_SYSTEM_PROMPT, AdapterCommand, BaseAdapter, agent_env, build_prompt


class ClaudeAdapter(BaseAdapter):
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        argv = [
            self._config.default_cli,
            *self._config.headless_args,
            "--allowed-tools",
            "Read,Write,Edit,Bash,Skill",
            "--append-system-prompt",
            STAGE_SYSTEM_PROMPT,
            "-p",
            build_prompt(task),
        ]
        return AdapterCommand(argv=argv, env=agent_env(task))
```

Create `runtime/agent_gateway/adapters/codex_adapter.py`:

```python
from __future__ import annotations

from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig

from .base import AdapterCommand, BaseAdapter, agent_env, build_prompt


class CodexAdapter(BaseAdapter):
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        argv = [
            self._config.default_cli,
            "-c",
            "approval_policy=never",
            "-c",
            "sandbox_mode=workspace-write",
            *self._config.headless_args,
            "exec",
            build_prompt(task),
        ]
        return AdapterCommand(argv=argv, env=agent_env(task))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/runtime/test_adapters.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add runtime/agent_gateway/adapters/ tests/runtime/test_adapters.py
git commit -m "feat(agent_gateway): add claude and codex adapters"
```

---

### Task 4: Kimi and Generic adapters

**Files:**
- Create: `runtime/agent_gateway/adapters/kimi_adapter.py`
- Create: `runtime/agent_gateway/adapters/generic_adapter.py`
- Test: `tests/runtime/test_adapters.py` (append)

**Interfaces:**
- Consumes: same base helpers as Task 3.
- Produces:
  - `KimiAdapter(config)` → argv `[default_cli, *headless_args, "-p", build_prompt(task)]`.
  - `GenericAdapter(config)` → argv `[default_cli, *headless_args, config.generic.prompt_flag, build_prompt(task)]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_adapters.py`:

```python
from runtime.agent_gateway.adapters.generic_adapter import GenericAdapter
from runtime.agent_gateway.adapters.kimi_adapter import KimiAdapter


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_adapters.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `runtime/agent_gateway/adapters/kimi_adapter.py`:

```python
from __future__ import annotations

from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig

from .base import AdapterCommand, BaseAdapter, agent_env, build_prompt


class KimiAdapter(BaseAdapter):
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        argv = [
            self._config.default_cli,
            *self._config.headless_args,
            "-p",
            build_prompt(task),
        ]
        return AdapterCommand(argv=argv, env=agent_env(task))
```

Create `runtime/agent_gateway/adapters/generic_adapter.py`:

```python
from __future__ import annotations

from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig

from .base import AdapterCommand, BaseAdapter, agent_env, build_prompt


class GenericAdapter(BaseAdapter):
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        argv = [
            self._config.default_cli,
            *self._config.headless_args,
            self._config.generic.prompt_flag,
            build_prompt(task),
        ]
        return AdapterCommand(argv=argv, env=agent_env(task))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/runtime/test_adapters.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add runtime/agent_gateway/adapters/ tests/runtime/test_adapters.py
git commit -m "feat(agent_gateway): add kimi and generic adapters"
```

---

### Task 5: Refactor `CliBackend` to the adapter contract

**Files:**
- Modify: `runtime/agent_gateway/backends/cli_backend.py` (full rewrite)
- Test: `tests/runtime/test_agent_driver.py` (rewrite the backend tests; driver tests come in Task 6)

**Interfaces:**
- Consumes: `BaseAdapter`/`AdapterCommand` (Tasks 2-4), `AgentConfig` (Task 1).
- Produces: `CliBackend(config: AgentConfig, adapter: BaseAdapter)` with unchanged `async run(task: AgentTask) -> AgentResult` signature. Behavior changes: argv comes from the adapter; subprocess env is `{**os.environ, **command.env}`; on missing `report.md` with non-empty stdout, stdout is written to `report.md` (downstream `agent_tool` reads that file); `FileNotFoundError` from spawn → `success=False` with `Agent CLI not found: <argv[0]>`.

- [ ] **Step 1: Rewrite the failing tests**

Replace the entire content of `tests/runtime/test_agent_driver.py` with:

```python
import asyncio
import sys
import textwrap
from unittest.mock import AsyncMock, patch

import pytest

from runtime.agent_gateway.adapters.base import AdapterCommand, BaseAdapter
from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.agent_gateway.backends.cli_backend import CliBackend
from runtime.config_loader import AgentConfig


class FakeAdapter(BaseAdapter):
    def __init__(self, argv: list[str]) -> None:
        self._argv = argv

    def compose_command(self, task: AgentTask) -> AdapterCommand:
        return AdapterCommand(
            argv=self._argv,
            env={"OQM_RUN_ID": task.pipeline_run_id, "OQM_OUTPUT_DIR": task.output_dir},
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
```

(The unused `AgentResult` import above is intentional only if your linter tolerates it — remove it if `ruff` flags it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_agent_driver.py -v`
Expected: FAIL — `CliBackend.__init__` takes only `config`, and no `--skill` flags exist anymore.

- [ ] **Step 3: Rewrite `cli_backend.py`**

Replace the entire content of `runtime/agent_gateway/backends/cli_backend.py` with:

```python
from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path

from runtime.agent_gateway.adapters.base import BaseAdapter
from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.config_loader import AgentConfig

from .base import BaseBackend


class CliBackend(BaseBackend):
    def __init__(self, config: AgentConfig, adapter: BaseAdapter) -> None:
        self._config = config
        self._adapter = adapter

    async def run(self, task: AgentTask) -> AgentResult:
        output_dir = Path(task.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        command = self._adapter.compose_command(task)
        env = {**os.environ, **command.env}

        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *command.argv,
                cwd=command.cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=task.timeout_sec
            )
        except FileNotFoundError:
            return AgentResult(
                success=False,
                error=f"Agent CLI not found: {command.argv[0]}",
            )
        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.kill()
                await proc.wait()
            return AgentResult(
                success=False,
                error=f"Agent process timed out after {task.timeout_sec}s",
            )

        if proc.returncode != 0:
            error_msg = (
                stderr.decode().strip()
                or stdout.decode().strip()
                or f"Agent process exited with code {proc.returncode}"
            )
            return AgentResult(success=False, error=error_msg)

        report_path = output_dir / "report.md"
        if report_path.exists():
            report_content = report_path.read_text(encoding="utf-8")
        else:
            report_content = stdout.decode(encoding="utf-8", errors="replace")
            if not report_content.strip():
                return AgentResult(
                    success=False,
                    error=f"Report not found at {report_path} and stdout was empty",
                )
            report_path.write_text(report_content, encoding="utf-8")

        summary = self._extract_summary(report_content)
        return AgentResult(
            success=True,
            report_artifact="report.md",
            summary=summary,
        )

    def _extract_summary(self, content: str) -> str:
        match = re.search(r"<!--\s*summary:\s*(.*?)\s*-->", content, re.DOTALL)
        if match:
            return match.group(1).strip()

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if lines:
            return lines[0]

        return ""
```

Notes vs. the old implementation: the flag-argument construction, `custom_command` shell path, and `_resolve_skill_path` are deleted; `shlex` import goes away; `os` is imported for env merging.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/runtime/test_agent_driver.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add runtime/agent_gateway/backends/cli_backend.py tests/runtime/test_agent_driver.py
git commit -m "refactor(agent_gateway): drive CliBackend via adapters with prompt contract"
```

---

### Task 6: `AgentDriver` selects adapter; delete MCP/HTTP backends

**Files:**
- Modify: `runtime/agent_gateway/agent_driver.py` (full rewrite)
- Delete: `runtime/agent_gateway/backends/mcp_backend.py`, `runtime/agent_gateway/backends/http_backend.py`
- Test: `tests/runtime/test_agent_driver.py` (append driver tests)

**Interfaces:**
- Consumes: all four adapters (Tasks 3-4), `CliBackend(config, adapter)` (Task 5).
- Produces: `AgentDriver(config: AgentConfig)` — `config.adapter` selects the adapter; unknown values raise `ValueError(f"Unknown agent adapter: {config.adapter}")` (defensive; `Literal` already constrains it). `async run(task)` unchanged.

- [ ] **Step 1: Write the failing tests**

Append to `tests/runtime/test_agent_driver.py`:

```python
from runtime.agent_gateway.adapters.claude_adapter import ClaudeAdapter
from runtime.agent_gateway.adapters.codex_adapter import CodexAdapter
from runtime.agent_gateway.adapters.generic_adapter import GenericAdapter
from runtime.agent_gateway.adapters.kimi_adapter import KimiAdapter
from runtime.agent_gateway.agent_driver import AgentDriver


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_agent_driver.py -k selects_adapter -v`
Expected: FAIL — current driver branches on `tool_callback` and imports MCP/HTTP backends.

- [ ] **Step 3: Rewrite `agent_driver.py`**

Replace the entire content of `runtime/agent_gateway/agent_driver.py` with:

```python
from __future__ import annotations

from runtime.agent_gateway.adapters.base import BaseAdapter
from runtime.agent_gateway.adapters.claude_adapter import ClaudeAdapter
from runtime.agent_gateway.adapters.codex_adapter import CodexAdapter
from runtime.agent_gateway.adapters.generic_adapter import GenericAdapter
from runtime.agent_gateway.adapters.kimi_adapter import KimiAdapter
from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask
from runtime.agent_gateway.backends.base import BaseBackend
from runtime.agent_gateway.backends.cli_backend import CliBackend
from runtime.config_loader import AgentConfig

_ADAPTERS: dict[str, type[BaseAdapter]] = {
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
    "kimi": KimiAdapter,
    "generic": GenericAdapter,
}


class AgentDriver:
    def __init__(self, config: AgentConfig) -> None:
        adapter_cls = _ADAPTERS.get(config.adapter)
        if adapter_cls is None:
            raise ValueError(f"Unknown agent adapter: {config.adapter}")
        self._backend: BaseBackend = CliBackend(config, adapter_cls(config))

    async def run(self, task: AgentTask) -> AgentResult:
        return await self._backend.run(task)
```

Delete the now-unreferenced backends:

```bash
git rm runtime/agent_gateway/backends/mcp_backend.py runtime/agent_gateway/backends/http_backend.py
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/runtime/test_agent_driver.py tests/runtime/test_adapters.py -v`
Expected: PASS. Then run the wider suite to catch stale references:

Run: `python -m pytest tests/runtime tests/tools -v`
Expected: PASS except `tests/integration/test_agent_demo_pipeline.py` (fixed in Task 9) and any test still importing `mcp_backend`/`http_backend` — if such imports exist (check with `grep -rn "mcp_backend\|http_backend" tests runtime`), delete those references as part of this task.

- [ ] **Step 5: Commit**

```bash
git add runtime/agent_gateway/ tests/runtime/test_agent_driver.py
git commit -m "refactor(agent_gateway): select CLI adapter in AgentDriver; drop mcp/http backends"
```

---

### Task 7: `init-workspace` module and templates

**Files:**
- Create: `runtime/workspace/__init__.py` (empty)
- Create: `runtime/workspace/init_workspace.py`
- Create: `templates/workspace/CLAUDE.md.tmpl`
- Create: `templates/workspace/AGENTS.md.tmpl`
- Create: `templates/workspace/settings.json.tmpl`
- Create: `templates/workspace/skills/oqm-tool.SKILL.md`
- Test: `tests/runtime/test_init_workspace.py`

**Interfaces:**
- Consumes: business skills from `skills/core/*.md` in the target project root.
- Produces:
  - `init_workspace(project_root: Path, targets: list[str], force: bool = False) -> list[Path]` — returns written paths; raises `ValueError` on unknown target.
  - Targets: `"claude"` → `CLAUDE.md`, `.claude/settings.json` (permission-merge), `.claude/skills/<name>/SKILL.md`; `"codex"`/`"kimi"` → `AGENTS.md`, `.agents/skills/<name>/SKILL.md`.
  - Existing files are skipped unless `force=True` (except `settings.json`, which is merged, not overwritten).

- [ ] **Step 1: Write the failing tests**

Create `tests/runtime/test_init_workspace.py`:

```python
import json

import pytest

from runtime.workspace.init_workspace import init_workspace


@pytest.fixture
def project_root(tmp_path):
    core = tmp_path / "skills" / "core"
    core.mkdir(parents=True)
    (core / "agent_demo.md").write_text("# agent_demo\n\nDo the demo.\n")
    return tmp_path


@pytest.mark.unit
def test_init_workspace_claude_target(project_root):
    written = init_workspace(project_root, ["claude"])

    assert project_root.joinpath("CLAUDE.md").exists()
    settings = json.loads(project_root.joinpath(".claude/settings.json").read_text())
    assert "Bash(python -m runtime.cli tool *)" in settings["permissions"]["allow"]
    assert project_root.joinpath(".claude/skills/oqm-tool/SKILL.md").exists()
    business = project_root.joinpath(".claude/skills/agent_demo/SKILL.md")
    assert business.exists()
    text = business.read_text()
    assert text.startswith("---\nname: agent_demo\ndescription: agent_demo\n---")
    assert "# agent_demo" in text
    assert not project_root.joinpath("AGENTS.md").exists()
    assert len(written) >= 4


@pytest.mark.unit
def test_init_workspace_codex_target(project_root):
    init_workspace(project_root, ["codex"])

    assert project_root.joinpath("AGENTS.md").exists()
    assert project_root.joinpath(".agents/skills/oqm-tool/SKILL.md").exists()
    assert project_root.joinpath(".agents/skills/agent_demo/SKILL.md").exists()
    assert not project_root.joinpath("CLAUDE.md").exists()


@pytest.mark.unit
def test_init_workspace_multiple_targets(project_root):
    init_workspace(project_root, ["claude", "kimi"])

    assert project_root.joinpath("CLAUDE.md").exists()
    assert project_root.joinpath("AGENTS.md").exists()


@pytest.mark.unit
def test_init_workspace_idempotent_without_force(project_root):
    init_workspace(project_root, ["claude"])
    claude_md = project_root / "CLAUDE.md"
    claude_md.write_text("user edits")
    (project_root / ".claude/settings.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(git *)"]}, "other": 1})
    )

    written = init_workspace(project_root, ["claude"])

    assert claude_md.read_text() == "user edits"
    settings = json.loads((project_root / ".claude/settings.json").read_text())
    assert "Bash(git *)" in settings["permissions"]["allow"]
    assert "Bash(python -m runtime.cli tool *)" in settings["permissions"]["allow"]
    assert settings["other"] == 1
    assert project_root / ".claude/settings.json" in written


@pytest.mark.unit
def test_init_workspace_force_overwrites(project_root):
    init_workspace(project_root, ["claude"])
    claude_md = project_root / "CLAUDE.md"
    claude_md.write_text("user edits")

    init_workspace(project_root, ["claude"], force=True)

    assert claude_md.read_text() != "user edits"


@pytest.mark.unit
def test_init_workspace_rejects_unknown_target(project_root):
    with pytest.raises(ValueError, match="Unknown agent target"):
        init_workspace(project_root, ["gpt"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_init_workspace.py -v`
Expected: FAIL with `ModuleNotFoundError: runtime.workspace`.

- [ ] **Step 3: Create templates**

`templates/workspace/CLAUDE.md.tmpl` and `templates/workspace/AGENTS.md.tmpl` (identical content in both files):

```markdown
# OpenQuantMaster

This project is OpenQuantMaster, a quant trading pipeline runtime (Python).

## Calling pipeline tools

Invoke registered tools through the runtime CLI:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json>'
```

The command prints a JSON `ToolResult` to stdout; check `success` before using `data`.
See the `oqm-tool` skill for details and examples.
```

`templates/workspace/settings.json.tmpl`:

```json
{
  "permissions": {
    "allow": [
      "Bash(python -m runtime.cli tool *)"
    ]
  }
}
```

`templates/workspace/skills/oqm-tool.SKILL.md`:

```markdown
---
name: oqm-tool
description: How to call OpenQuantMaster pipeline tools from the shell. Use when a task needs data fetching, signal scanning, backtesting, notifications, or any other registered OpenQuantMaster tool.
---

# Calling OpenQuantMaster tools

All registered tools are invoked through the runtime CLI:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json>'
```

Rules:

- The command prints a JSON `ToolResult` to stdout. Always check the `success` field before using `data`.
- Tool input schemas live in `tools/<domain>/<tool_name>.py` (the `input_model` class). Read the source if unsure about parameters.
- Currently registered tools include: `demo_data_tool`, `notify_tool`, `ohlcv_tool`, `signal_scan_tool`, `backtest_tool`, `agent_tool`.

Examples:

```bash
python -m runtime.cli tool ohlcv_tool --inputs '{"symbol":"BTC/USDT","timeframe":"1h","limit":100}'
python -m runtime.cli tool notify_tool --inputs '{"subject":"Report","body":"...","channels":["pushplus"]}'
```
```

- [ ] **Step 4: Implement the module**

Create `runtime/workspace/__init__.py` (empty file).

Create `runtime/workspace/init_workspace.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "workspace"

ALL_TARGETS = frozenset({"claude", "codex", "kimi"})
_AGENTS_TARGETS = frozenset({"codex", "kimi"})


def init_workspace(project_root: Path, targets: list[str], force: bool = False) -> list[Path]:
    unknown = set(targets) - ALL_TARGETS
    if unknown:
        raise ValueError(f"Unknown agent target(s): {sorted(unknown)}")

    project_root = project_root.resolve()
    skills = _load_skills(project_root)
    written: list[Path] = []

    if "claude" in targets:
        written += _write(project_root / "CLAUDE.md", _render("CLAUDE.md.tmpl"), force)
        written += _merge_settings(project_root / ".claude" / "settings.json")
        for name, body in skills:
            written += _write(project_root / ".claude" / "skills" / name / "SKILL.md", body, force)

    if _AGENTS_TARGETS & set(targets):
        written += _write(project_root / "AGENTS.md", _render("AGENTS.md.tmpl"), force)
        for name, body in skills:
            written += _write(project_root / ".agents" / "skills" / name / "SKILL.md", body, force)

    return written


def _render(template_name: str) -> str:
    return (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")


def _load_skills(project_root: Path) -> list[tuple[str, str]]:
    skills: list[tuple[str, str]] = [
        ("oqm-tool", _render("skills/oqm-tool.SKILL.md")),
    ]
    core_dir = project_root / "skills" / "core"
    if core_dir.is_dir():
        for md in sorted(core_dir.glob("*.md")):
            skills.append((md.stem, _to_skill(md)))
    return skills


def _to_skill(md_path: Path) -> str:
    body = md_path.read_text(encoding="utf-8")
    description = md_path.stem
    for line in body.splitlines():
        if line.startswith("# "):
            description = line[2:].strip()
            break
    return f"---\nname: {md_path.stem}\ndescription: {description}\n---\n\n{body}"


def _write(path: Path, content: str, force: bool) -> list[Path]:
    if path.exists() and not force:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return [path]


def _merge_settings(path: Path) -> list[Path]:
    template = json.loads(_render("settings.json.tmpl"))
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    else:
        settings = {}
    allow = settings.setdefault("permissions", {}).setdefault("allow", [])
    for rule in template["permissions"]["allow"]:
        if rule not in allow:
            allow.append(rule)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    return [path]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/runtime/test_init_workspace.py -v`
Expected: PASS (6 tests).

- [ ] **Step 6: Commit**

```bash
git add runtime/workspace/ templates/workspace/ tests/runtime/test_init_workspace.py
git commit -m "feat(workspace): add init-workspace generator with claude/codex targets"
```

---

### Task 8: `init-workspace` CLI subcommand

**Files:**
- Modify: `runtime/cli.py`
- Test: `tests/runtime/test_init_workspace.py` (append CLI test)

**Interfaces:**
- Consumes: `runtime.workspace.init_workspace.init_workspace` (Task 7).
- Produces: `python -m runtime.cli init-workspace --agent <claude|codex|kimi> [--agent ...] [--force] [--root PATH]`. `--agent` is required and repeatable.

- [ ] **Step 1: Write the failing test**

Append to `tests/runtime/test_init_workspace.py`:

```python
from click.testing import CliRunner

from runtime.cli import cli


@pytest.mark.unit
def test_init_workspace_cli(tmp_path):
    (tmp_path / "skills" / "core").mkdir(parents=True)
    runner = CliRunner()

    result = runner.invoke(cli, ["init-workspace", "--agent", "claude", "--root", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert (tmp_path / "CLAUDE.md").exists()
    assert "wrote" in result.output


@pytest.mark.unit
def test_init_workspace_cli_requires_agent(tmp_path):
    runner = CliRunner()

    result = runner.invoke(cli, ["init-workspace", "--root", str(tmp_path)])

    assert result.exit_code != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/runtime/test_init_workspace.py -k cli -v`
Expected: FAIL — `cli` has no `init-workspace` command.

- [ ] **Step 3: Add the subcommand**

In `runtime/cli.py`, add after the `tool` command (before `if __name__ == "__main__":`):

```python
@cli.command(name="init-workspace")
@click.option(
    "--agent",
    "agents",
    multiple=True,
    required=True,
    type=click.Choice(["claude", "codex", "kimi"]),
    help="Target agent CLI. Repeatable.",
)
@click.option("--force", is_flag=True, help="Overwrite existing files.")
@click.option(
    "--root",
    type=click.Path(path_type=Path, file_okay=False),
    default=Path("."),
    help="Project root to initialize.",
)
def init_workspace(agents: tuple[str, ...], force: bool, root: Path) -> None:
    from runtime.workspace.init_workspace import init_workspace as _init

    written = _init(root, list(agents), force=force)
    if not written:
        click.echo("Nothing to write (all files exist; use --force to overwrite).")
    for path in written:
        click.echo(f"wrote {path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/runtime/test_init_workspace.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Smoke-test against the real repo**

Run: `python -m runtime.cli init-workspace --agent claude --root .`
Expected: prints `wrote CLAUDE.md`, `wrote .claude/settings.json`, `wrote .claude/skills/...` for `oqm-tool` and each `skills/core/*.md`. Run it again and confirm `CLAUDE.md` is skipped on the second run.

Decide with the project owner whether the generated `CLAUDE.md` / `.claude/` should be committed or gitignored — if this repo's own assistant config should stay as-is, add them to `.gitignore` instead and revert the smoke-test artifacts (`git checkout -- .` / delete untracked generated files). Do NOT commit generated workspace files as part of this task.

- [ ] **Step 6: Commit**

```bash
git add runtime/cli.py tests/runtime/test_init_workspace.py
git commit -m "feat(cli): add init-workspace subcommand"
```

---

### Task 9: Migrate `agent_demo` integration test; remove demo CLI script

**Files:**
- Modify: `tests/integration/test_agent_demo_pipeline.py`
- Delete: `scripts/agent_demo_cli.py`
- Test: `tests/integration/test_agent_demo_pipeline.py`

**Interfaces:**
- Consumes: new `AgentConfig` (Task 1), adapter-driven `CliBackend` (Task 5).
- Produces: end-to-end proof that `agent_demo` runs on the prompt contract with a fake CLI executable.

- [ ] **Step 1: Rewrite the fixture's fake CLI and config**

In `tests/integration/test_agent_demo_pipeline.py`, replace the `fake_script` content with:

```python
    fake_script = tmp_path / "fake_agent_cli.py"
    fake_script.write_text(
        textwrap.dedent(
            """
            import argparse
            import json
            import os
            import pathlib
            import re

            parser = argparse.ArgumentParser()
            parser.add_argument("-p", dest="prompt", default="")
            args, _unknown = parser.parse_known_args()

            output_dir = pathlib.Path(os.environ["OQM_OUTPUT_DIR"])
            output_dir.mkdir(parents=True, exist_ok=True)

            match = re.search(r"阅读上一阶段产物 (\\S+)", args.prompt)
            data = {"topic": "unknown", "data": []}
            if match:
                data = json.loads(pathlib.Path(match.group(1)).read_text(encoding="utf-8"))

            (output_dir / "report.md").write_text(
                f"# Analysis\\n\\n"
                f"Topic: {data['topic']}\\n"
                f"Signals: {len(data['data'])} rows\\n\\n"
                f"<!-- summary: The demo signals are bullish. -->\\n"
            )
            """
        )
    )
```

Replace the `agent:` section of the fixture's `config_path.write_text(...)` with:

```python
agent:
  adapter: claude
  default_cli: {sys.executable}
  headless_args:
    - {fake_script}
```

(Remove the `custom_command` and `tool_callback` lines.)

- [ ] **Step 2: Run the integration test**

Run: `python -m pytest tests/integration/test_agent_demo_pipeline.py -v`
Expected: PASS — the Claude adapter argv becomes `[python, fake_script, --allowed-tools, ..., --append-system-prompt, ..., -p, <prompt>]`; the fake script extracts the artifact path from the prompt, writes `report.md` into `$OQM_OUTPUT_DIR`, and the notify stage receives `"The demo signals are bullish."`.

- [ ] **Step 3: Delete the old demo script**

```bash
git rm scripts/agent_demo_cli.py
```

Check for other references first: `grep -rn "agent_demo_cli" --include='*.py' --include='*.yaml' --include='*.md' . | grep -v docs/superpowers` — the only remaining hit should be none (Task 1 already removed it from `config.yaml`; Task 10 handles docs).

- [ ] **Step 4: Run the full suite**

Run: `python -m pytest -v`
Expected: all PASS. Also run `ruff check runtime tools tests` — fix anything it flags.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/test_agent_demo_pipeline.py scripts/
git commit -m "test(integration): migrate agent_demo to prompt contract; remove demo CLI script"
```

---

### Task 10: Update `AGENT_GUIDE.md`

**Files:**
- Modify: `AGENT_GUIDE.md:12-33`

**Interfaces:**
- Consumes: everything above.
- Produces: user-facing docs for `init-workspace` and the new `agent:` config.

- [ ] **Step 1: Replace the demo section**

Replace lines 12-33 (the "## Agent Integration Demo" section through the end of the file) with:

```markdown
## Agent Integration

Pipeline Agent stages invoke a real Agent CLI (`claude`, `codex`, `kimi`, or a
`generic` CLI) headlessly with a minimal prompt. The Agent reads skills and
artifacts itself and writes its report to `$OQM_OUTPUT_DIR/report.md`.

Initialize this repo as an Agent workspace before running Agent stages:

```bash
python -m runtime.cli init-workspace --agent claude   # and/or: --agent codex --agent kimi
```

This generates `CLAUDE.md`/`AGENTS.md`, `.claude/` or `.agents/` skill folders
(including the `oqm-tool` skill and synced business skills from `skills/core/`),
and merges tool-call permissions into `.claude/settings.json`.

Configure the CLI in `config.yaml`:

```yaml
agent:
  adapter: "claude"        # claude | codex | kimi | generic
  default_cli: "claude"
  timeout_sec: 300
  headless_args: []
```

Run the demo pipeline:

```bash
quantmaster-daemon --run agent_demo
```

Stages:
1. `generate_data` — writes `demo_data.json`.
2. `agent_analyze` — invokes the configured Agent CLI with skill `skills/core/agent_demo.md`.
3. `notify` — sends the summary via PushPlus.

Set the PushPlus token via environment variable `QUANT_AGENT_NOTIFIER__PUSHPLUS__TOKEN`.

For manual tool invocation:

```bash
python -m runtime.cli tool <tool_name> --inputs '<json_string>'
```
```

- [ ] **Step 2: Verify markdown renders**

Run: `cat AGENT_GUIDE.md` and confirm the replaced section reads correctly (nested code fences inside the replacement use three backticks — ensure no fence collisions).

- [ ] **Step 3: Commit**

```bash
git add AGENT_GUIDE.md
git commit -m "docs: document init-workspace and adapter-based agent config"
```

---

## Self-Review Notes

- Spec coverage: §2 adapters (Tasks 2-6), §3 init-workspace (Tasks 7-8), §4 invocation incl. `--append-system-prompt` (Task 3), §5 output recovery + stdout fallback (Task 5), §7 config (Task 1), §8 file changes (all tasks; memory files deferred per §1.2), §9 tests (Tasks 1, 5-9), §10 migration (Tasks 6, 9, 10).
- `AGENTS.md`/`CLAUDE.md` templates contain no stage contract or trade constraints (owner amendment, commit 3984159).
- `kimi` adapter uses `-p` pending confirmation of Kimi's real headless flag (spec §4); the `generic` adapter covers CLIs with different flags.
- Pre-existing wart kept out of scope: `tools/agent/agent_tool.py:47-50` hardcodes the previous-stage artifact path to `generate_data/demo_data.json`; generalizing it belongs to the full design, not this plan.
