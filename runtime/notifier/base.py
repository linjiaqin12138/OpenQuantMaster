from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Notifier(ABC):
    def __init__(self, config: Any) -> None:
        self._config = config

    @abstractmethod
    async def send(self, subject: str, body: str) -> dict[str, Any]:
        ...
