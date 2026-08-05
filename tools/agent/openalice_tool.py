from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar

import structlog
from pydantic import BaseModel, Field

from runtime.config_loader import RuntimeConfig, load_config
from runtime.openalice_client import OpenAliceClient, OpenAliceError
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ToolResult

logger = structlog.get_logger()

PROMPT_MAX_CHARS = 16000


class OpenAliceToolInput(BaseModel):
    prompt: str = Field(min_length=1)
    context: dict[str, Any] | None = None
    wait: bool = True
    timeout_sec: int | None = Field(default=None, ge=1, le=1800)
    resume: bool = True
    pipeline_run_id: str | None = None


class OpenAliceToolOutput(BaseModel):
    success: bool
    response: str
    session_id: str
    task_id: str
    status: str
    truncated: bool


class OpenAliceTool(BaseTool):
    name: ClassVar[str] = "openalice_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "agent_gateway"
    cost_estimate_usd: ClassVar[float] = 0.0
    fallback_tools: ClassVar[list[str]] = []
    input_model: ClassVar[type[BaseModel]] = OpenAliceToolInput
    output_model: ClassVar[type[BaseModel]] = OpenAliceToolOutput

    def __init__(
        self,
        openalice_client: OpenAliceClient | None = None,
        session_path: Path | str | None = None,
    ) -> None:
        self._openalice_client: OpenAliceClient | None = openalice_client
        self._session_path: Path | None = Path(session_path) if session_path else None

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        validated = self.input_model(**inputs)
        cfg = self._load_config()
        client = self._openalice_client or OpenAliceClient(cfg.openalice)
        session_path = (
            self._session_path
            or Path(cfg.paths.database).parent / "openalice_session.json"
        )

        prompt = validated.prompt
        if validated.context is not None:
            context_json = json.dumps(validated.context, ensure_ascii=False, default=str)
            prompt = f"{prompt}\n\n[上下文数据 JSON]\n{context_json}"
        truncated = False
        if len(prompt) > PROMPT_MAX_CHARS:
            logger.warning(
                "openalice.prompt_truncated",
                original_length=len(prompt),
                max_chars=PROMPT_MAX_CHARS,
            )
            prompt = prompt[:PROMPT_MAX_CHARS]
            truncated = True

        timeout_sec = validated.timeout_sec or cfg.openalice.default_timeout
        resume_id = (
            self._load_resume_id(session_path, cfg.openalice.workspace_id)
            if validated.resume
            else None
        )

        try:
            result = await client.conversation_ask(
                prompt=prompt,
                timeout_sec=timeout_sec,
                resume_id=resume_id,
                wait=validated.wait,
            )
            if self._is_unavailable(result):
                # Stored resumeId is gone server-side: drop it and start a fresh session.
                logger.warning(
                    "openalice.resume_invalid",
                    reason=(result.get("resolution") or {}).get("reason"),
                )
                result = await client.conversation_ask(
                    prompt=prompt,
                    timeout_sec=timeout_sec,
                    resume_id=None,
                    wait=validated.wait,
                )
        except OpenAliceError as exc:
            logger.error("openalice.conversation_ask_failed", error=str(exc))
            return ToolResult(success=False, error=f"OpenAlice gateway error: {exc}")

        if not result.get("ok"):
            error = result.get("error") or result.get("status") or "unknown error"
            logger.error("openalice.conversation_ask_rejected", error=str(error))
            return ToolResult(success=False, error=f"OpenAlice conversation_ask failed: {error}")

        status = str(result.get("status", ""))
        if validated.wait and status != "done":
            error = result.get("error") or f"task ended with status {status!r}"
            logger.error("openalice.task_not_done", status=status, error=str(error))
            return ToolResult(success=False, error=f"OpenAlice conversation_ask failed: {error}")

        new_resume_id = str(result.get("resumeId", ""))
        if new_resume_id:
            self._save_resume_id(session_path, cfg.openalice.workspace_id, new_resume_id)

        output = self.output_model(
            success=True,
            response=str(result.get("assistantText") or ""),
            session_id=new_resume_id,
            task_id=str(result.get("taskId", "")),
            status=status,
            truncated=truncated,
        )
        return ToolResult(success=True, data=output.model_dump())

    @staticmethod
    def _is_unavailable(result: dict[str, Any]) -> bool:
        return result.get("ok") is False and result.get("status") == "unavailable"

    @staticmethod
    def _load_config() -> RuntimeConfig:
        try:
            return load_config()
        except FileNotFoundError:
            return RuntimeConfig()

    @staticmethod
    def _load_resume_id(path: Path, workspace_id: str) -> str | None:
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("openalice.session_file_corrupt", path=str(path), error=str(exc))
            return None
        entry = data.get(workspace_id) if isinstance(data, dict) else None
        if isinstance(entry, dict):
            resume_id = entry.get("resume_id")
            if isinstance(resume_id, str) and resume_id:
                return resume_id
        return None

    @staticmethod
    def _save_resume_id(path: Path, workspace_id: str, resume_id: str) -> None:
        data: dict[str, Any] = {}
        if path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (json.JSONDecodeError, OSError):
                data = {}
        data[workspace_id] = {
            "resume_id": resume_id,
            "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_path.replace(path)
