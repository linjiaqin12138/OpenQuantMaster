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
