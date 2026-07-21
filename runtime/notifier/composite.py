from __future__ import annotations

from typing import Any

from runtime.config_loader import NotifierConfig
from runtime.notifier.base import Notifier
from runtime.notifier.email_notifier import EmailNotifier
from runtime.notifier.pushplus_notifier import PushplusNotifier
from runtime.notifier.telegram_notifier import TelegramNotifier


class CompositeNotifier(Notifier):
    def __init__(self, config: NotifierConfig) -> None:
        self._notifiers: dict[str, Notifier] = {}
        if config.pushplus.enabled:
            self._notifiers["pushplus"] = PushplusNotifier(config.pushplus)
        if config.telegram.enabled:
            self._notifiers["telegram"] = TelegramNotifier(config.telegram)
        if config.email.enabled:
            self._notifiers["email"] = EmailNotifier(config.email)

    async def send(self, subject: str, body: str) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, notifier in self._notifiers.items():
            results.update(await notifier.send(subject, body))
        return results


def build_notifier(config: NotifierConfig) -> CompositeNotifier:
    return CompositeNotifier(config)
