from __future__ import annotations

from typing import Any

import httpx

from runtime.notifier.base import Notifier


class PushplusNotifier(Notifier):
    async def send(self, subject: str, body: str) -> dict[str, Any]:
        token = self._config.token
        if not token:
            return {"pushplus": "missing token", "success": False}

        payload = {
            "token": token,
            "title": subject,
            "content": body,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            try:
                resp = await client.post("http://www.pushplus.plus/send", json=payload)
                resp.raise_for_status()
                return {"pushplus": "ok"}
            except Exception as exc:
                return {"pushplus": f"error: {exc}", "success": False}
