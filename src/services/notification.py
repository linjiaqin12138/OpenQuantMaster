from __future__ import annotations

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from src.config import AppConfig, NotificationConfig
from src.operations.pushplus import send_pushplus
from src.services.base import BaseService, ServiceResult

NotificationFormat = Literal["html", "txt", "markdown", "json"]


class NotificationInput(BaseModel):
    title: str = ""
    content: str = Field(..., min_length=1)
    format: NotificationFormat = "html"


class NotificationOutput(BaseModel):
    provider: str
    format: NotificationFormat
    message_id: str | None = None
    response: dict[str, Any]


class NotificationService(BaseService):
    input_model: ClassVar[type[BaseModel]] = NotificationInput
    output_model: ClassVar[type[BaseModel]] = NotificationOutput

    def __init__(self, cfg: NotificationConfig) -> None:
        self.cfg = cfg

    @classmethod
    def from_config(cls, config: AppConfig) -> NotificationService:
        return cls(NotificationConfig(pushplus=config.providers.pushplus))

    async def _run(self, inputs: NotificationInput) -> ServiceResult:
        if self.cfg.provider == "pushplus":
            return await self._send_with_pushplus(inputs)
        return ServiceResult.from_error(
            "unsupported_provider",
            f"Unsupported notification provider: {self.cfg.provider}",
        )

    async def _send_with_pushplus(self, inputs: NotificationInput) -> ServiceResult:
        provider = self.cfg.pushplus
        if not provider.token:
            return ServiceResult.from_error(
                "missing_provider_token",
                "PushPlus token is required",
            )
        result = await send_pushplus(
            token=provider.token,
            title=inputs.title,
            content=inputs.content,
            template=inputs.format,
            channel=provider.channel,
            timeout_seconds=provider.timeout_seconds,
        )
        if not result.success:
            return ServiceResult(
                success=False,
                error=result.error,
            )

        response = result.data
        message_id = response.get("data")
        output = self.output_model(
            provider=self.cfg.provider,
            format=inputs.format,
            message_id=str(message_id) if message_id is not None else None,
            response=response,
        )
        return ServiceResult(success=True, data=output.model_dump())
