from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from src.models.result import ServiceResult
from src.services.base import BaseService
from src.use_cases.notification import (
    SendNotificationInput,
    SendNotificationOutput,
    SendNotificationUseCase,
    SendNotificationUseCaseConfig,
)

__all__ = [
    "NotificationService",
    "NotificationServiceConfig",
    "SendNotificationInput",
    "SendNotificationOutput",
]


class NotificationServiceConfig(BaseModel):
    """Configuration of the notification capability."""

    provider: Literal["pushplus"] = "pushplus"
    token: str = ""
    channel: str = "wechat"
    timeout_seconds: float = 10


class NotificationService(BaseService):
    """Notification capability: deliver one message through the configured provider."""

    def __init__(self, config: NotificationServiceConfig) -> None:
        self.config = config
        self._send = SendNotificationUseCase(
            SendNotificationUseCaseConfig(
                provider=config.provider,
                token=config.token,
                channel=config.channel,
                timeout_seconds=config.timeout_seconds,
            )
        )

    async def send(
        self,
        request: SendNotificationInput | dict[str, Any],
    ) -> ServiceResult:
        """Deliver one notification through the configured provider."""
        return await self._send.run(request)
