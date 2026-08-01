from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

from runtime.config_loader import OpenAliceConfig

logger = structlog.get_logger()


class OpenAliceError(RuntimeError):
    """Raised when the OpenAlice CLI gateway returns an error or malformed payload."""


class OpenAliceClient:
    """Async HTTP client for the OpenAlice CLI gateway.

    The gateway is OpenAlice's machine-facing surface (open posture, no auth —
    the workspace CLI carries no secret). One invoke endpoint serves every
    export: ``POST {cli_gateway_url}/cli/{workspace_id}/{export}/invoke`` with
    body ``{"tool": <name>, "args": {...}}``; the response is an MCP-style
    envelope whose ``content[0].text`` holds the JSON payload.
    """

    def __init__(self, config: OpenAliceConfig, timeout: float = 30.0) -> None:
        self._config = config
        self._timeout = timeout

    def _endpoint(self, export: str | None = None) -> str:
        base = self._config.cli_gateway_url.rstrip("/")
        exp = export or self._config.export
        return f"{base}/cli/{self._config.workspace_id}/{exp}/invoke"

    async def invoke(
        self,
        tool: str,
        args: dict[str, Any],
        export: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Post a generic tool invocation and return the parsed inner JSON payload."""
        payload = {"tool": tool, "args": args}
        url = self._endpoint(export)
        try:
            async with httpx.AsyncClient(timeout=timeout or self._timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise OpenAliceError(f"OpenAlice gateway request failed: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OpenAliceError(f"OpenAlice gateway returned invalid JSON: {exc}") from exc

        content = body.get("content") if isinstance(body, dict) else None
        if not isinstance(content, list) or not content:
            raise OpenAliceError("OpenAlice gateway response missing 'content' array")

        text = content[0].get("text") if isinstance(content[0], dict) else None
        if not isinstance(text, str):
            raise OpenAliceError("OpenAlice gateway response missing content[0].text")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise OpenAliceError(f"OpenAlice content text is not valid JSON: {exc}") from exc

        if not isinstance(parsed, dict):
            raise OpenAliceError("OpenAlice content text did not decode to a JSON object")

        return parsed

    async def conversation_ask(
        self,
        prompt: str,
        timeout_sec: float,
        resume_id: str | None = None,
        wait: bool = True,
    ) -> dict[str, Any]:
        """Invoke the agent via the workspace export's conversation_ask tool.

        Returns the raw result dict; callers must interpret ``ok``/``status``
        (success is ``ok and status == "done"``; a stale resumeId comes back as
        ``{"ok": False, "status": "unavailable"}``).
        """
        args: dict[str, Any] = {
            "prompt": prompt,
            "timeoutMs": int(timeout_sec * 1000),
            "await": wait,
        }
        if resume_id:
            args["resumeId"] = resume_id
        else:
            args["wsId"] = self._config.workspace_id

        logger.debug(
            "openalice.conversation_ask.request",
            resume_id=resume_id,
            wait=wait,
            timeout_sec=timeout_sec,
        )
        # await:true blocks server-side up to timeoutMs; give the HTTP call headroom.
        result = await self.invoke(
            "conversation_ask",
            args,
            export="workspace",
            timeout=(timeout_sec + 30.0) if wait else self._timeout,
        )
        logger.debug(
            "openalice.conversation_ask.response",
            ok=result.get("ok"),
            status=result.get("status"),
            task_id=result.get("taskId"),
        )
        return result

    async def window_rss(
        self,
        from_time: str,
        to: str | None = None,
        limit: int = 100,
        pattern: str | None = None,
    ) -> dict[str, Any]:
        """Fetch recent RSS articles through the OpenAlice windowRss tool."""
        args: dict[str, Any] = {"from": from_time, "limit": limit}
        if to is not None:
            args["to"] = to
        if pattern is not None:
            args["pattern"] = pattern

        logger.debug(
            "openalice.window_rss.request",
            from_time=from_time,
            limit=limit,
        )
        result = await self.invoke("windowRss", args)
        logger.debug(
            "openalice.window_rss.response",
            total=result.get("total"),
            shown=result.get("shown"),
        )
        return result

    async def read_rss(self, article_id: int) -> dict[str, Any]:
        """Fetch a single full RSS article by stable id via readRss."""
        logger.debug("openalice.read_rss.request", article_id=article_id)
        result = await self.invoke("readRss", {"id": article_id})
        if "error" in result:
            raise OpenAliceError(f"readRss failed for id {article_id}: {result['error']}")
        logger.debug("openalice.read_rss.response", article_id=article_id)
        return result
