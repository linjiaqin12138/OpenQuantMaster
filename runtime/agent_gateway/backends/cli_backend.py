from __future__ import annotations

import asyncio
import re
import shlex
from pathlib import Path

from runtime.agent_gateway.agent_result import AgentResult
from runtime.agent_gateway.agent_task import AgentTask

from .base import BaseBackend


class CliBackend(BaseBackend):
    async def run(self, task: AgentTask) -> AgentResult:
        skill_path = self._resolve_skill_path(task.skill_path)
        output_dir = Path(task.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        args = [
            "--skill",
            str(skill_path),
            "--artifact",
            task.previous_artifact_path,
            "--output-dir",
            str(output_dir),
            "--task",
            task.task_description,
        ]

        try:
            if self._config.custom_command:
                cmd = self._config.custom_command + " " + " ".join(
                    shlex.quote(arg) for arg in args
                )
                proc = await asyncio.create_subprocess_shell(
                    cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                cmd = [self._config.default_cli, *self._config.headless_args, *args]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=task.timeout_sec
            )
        except asyncio.TimeoutError:
            if proc.returncode is None:
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
        if not report_path.exists():
            return AgentResult(
                success=False,
                error=f"Report not found at {report_path}",
            )

        report_content = report_path.read_text(encoding="utf-8")
        summary = self._extract_summary(report_content)
        return AgentResult(
            success=True,
            report_artifact="report.md",
            summary=summary,
        )

    def _resolve_skill_path(self, skill_path: str) -> Path:
        path = Path(skill_path)
        if path.is_absolute() or path.exists():
            return path

        candidate = Path("skills") / skill_path
        if candidate.exists():
            return candidate

        candidate_md = candidate.with_suffix(".md")
        if candidate_md.exists():
            return candidate_md

        return candidate

    def _extract_summary(self, content: str) -> str:
        match = re.search(r"<!--\s*summary:\s*(.*?)\s*-->", content, re.DOTALL)
        if match:
            return match.group(1).strip()

        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if lines:
            return lines[0]

        return ""
