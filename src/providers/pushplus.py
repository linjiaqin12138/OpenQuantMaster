from __future__ import annotations

from typing import Any

import httpx

from src.models.result import AppError, Error, as_call_result

_PUSHPLUS_ENDPOINT = "https://www.pushplus.plus/send"


async def send_pushplus(
    *,
    token: str,
    title: str,
    content: str,
    template: str,
    channel: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Send one notification through PushPlus and return the raw response body."""
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": template,
        "channel": channel,
    }
    async with httpx.AsyncClient(timeout=timeout_seconds) as client:
        response = await client.post(_PUSHPLUS_ENDPOINT, json=payload)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise AppError(
            "provider_invalid_response",
            "PushPlus returned a non-object response",
        )
    if result.get("code") != 200:
        raise AppError(
            "provider_rejected",
            str(result.get("msg") or "PushPlus rejected the notification"),
        )
    return result


def map_pushplus_error(exc: Exception) -> Error | None:
    if isinstance(exc, httpx.TimeoutException):
        return Error(code="provider_timeout", message=str(exc), exception=exc)
    if isinstance(exc, httpx.ConnectError):
        return Error(code="provider_unavailable", message=str(exc), exception=exc)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return Error(code="provider_unauthorized", message=str(exc), exception=exc)
        if status == 429:
            return Error(code="provider_rate_limited", message=str(exc), exception=exc)
        return Error(code="provider_rejected", message=str(exc), exception=exc)
    if isinstance(exc, ValueError):
        return Error(code="provider_invalid_response", message=str(exc), exception=exc)
    return None


send_pushplus_result = as_call_result(send_pushplus, map_error=map_pushplus_error)
