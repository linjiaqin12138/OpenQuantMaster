from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.models.result import ServiceResult
from src.providers.pushplus import send_pushplus_result
from src.use_cases.base import BaseUseCase, provider_failure

NotificationFormat = Literal["html", "txt", "markdown", "json"]

_NOTIFICATION_ERROR_CODES = {
    "provider_timeout": "notification_unavailable",
    "provider_unavailable": "notification_unavailable",
    "provider_rate_limited": "notification_unavailable",
    "provider_rejected": "notification_rejected",
    "provider_unauthorized": "notification_rejected",
}


class SendNotificationInput(BaseModel):
    """Request of the notification action."""

    title: str = ""
    content: str = Field(..., min_length=1)
    format: NotificationFormat = "html"


class SendNotificationOutput(BaseModel):
    """Response of the notification action."""

    provider: str
    format: NotificationFormat
    message_id: str | None = None
    response: dict[str, Any]


class SendNotificationUseCaseConfig(BaseModel):
    """Settings of the notification workflow."""

    provider: Literal["pushplus"] = "pushplus"
    token: str = ""
    channel: str = "wechat"
    timeout_seconds: float = 10


class SendNotificationUseCase(BaseUseCase[SendNotificationInput, SendNotificationOutput]):
    """Deliver one notification through the configured provider."""

    input_model = SendNotificationInput
    output_model = SendNotificationOutput

    def __init__(self, config: SendNotificationUseCaseConfig) -> None:
        self._config = config

    async def _run(self, inputs: SendNotificationInput) -> ServiceResult:
        if self._config.provider != "pushplus":
            return ServiceResult.from_error(
                "unsupported_provider",
                f"Unsupported notification provider: {self._config.provider}",
            )

        if not self._config.token:
            return ServiceResult.from_error(
                "missing_provider_token",
                "PushPlus token is required",
            )

        result = await send_pushplus_result(
            token=self._config.token,
            title=inputs.title,
            content=inputs.content,
            template=inputs.format,
            channel=self._config.channel,
            timeout_seconds=self._config.timeout_seconds,
        )
        if not result.success:
            return provider_failure(
                result.error,
                codes=_NOTIFICATION_ERROR_CODES,
                default="notification_failed",
            )

        response = result.data
        message_id = response.get("data")
        output = SendNotificationOutput(
            provider=self._config.provider,
            format=inputs.format,
            message_id=str(message_id) if message_id is not None else None,
            response=response,
        )
        return ServiceResult(success=True, data=output)
