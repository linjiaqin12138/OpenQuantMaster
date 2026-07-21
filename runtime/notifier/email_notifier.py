from __future__ import annotations

from typing import Any

from runtime.notifier.base import Notifier


class EmailNotifier(Notifier):
    async def send(self, subject: str, body: str) -> dict[str, Any]:
        return {"email": "not_implemented"}
