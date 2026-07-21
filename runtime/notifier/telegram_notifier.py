from __future__ import annotations

from typing import Any

from runtime.notifier.base import Notifier


class TelegramNotifier(Notifier):
    async def send(self, subject: str, body: str) -> dict[str, Any]:
        return {"telegram": "not_implemented"}
