from __future__ import annotations

import httpx

from src.operations.base import OperationResult


async def send_pushplus(
    *,
    token: str,
    title: str,
    content: str,
    template: str,
    channel: str,
    timeout_seconds: float,
) -> OperationResult:
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": template,
        "channel": channel,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post("https://www.pushplus.plus/send", json=payload)
        response.raise_for_status()
        result = response.json()
    except httpx.HTTPError as exc:
        return OperationResult.from_error("provider_request_failed", str(exc), exc)
    except ValueError as exc:
        return OperationResult.from_error("invalid_provider_response", str(exc), exc)

    if not isinstance(result, dict):
        return OperationResult.from_error(
            "invalid_provider_response",
            "PushPlus returned a non-object response",
        )
    if result.get("code") != 200:
        return OperationResult.from_error(
            "provider_rejected",
            str(result.get("msg") or "PushPlus rejected the notification"),
        )
    return OperationResult(success=True, data=result)
