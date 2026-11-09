from __future__ import annotations

from src.models.result import Error


def map_requests_error(exc: Exception) -> Error | None:
    """Map ``requests``-style transport failures used by the SDK-based providers.

    Provider-specific mapping functions live in their own provider module; this
    helper only covers the transport errors the SDKs share.
    """
    try:
        import requests
    except ImportError:  # pragma: no cover - requests ships with the SDKs
        return None
    if isinstance(exc, requests.exceptions.Timeout):
        return Error(code="provider_timeout", message=str(exc), exception=exc)
    if isinstance(exc, requests.exceptions.ConnectionError):
        return Error(code="provider_unavailable", message=str(exc), exception=exc)
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(exc.response, "status_code", None)
        if status in (401, 403):
            return Error(code="provider_unauthorized", message=str(exc), exception=exc)
        if status == 429:
            return Error(code="provider_rate_limited", message=str(exc), exception=exc)
        return Error(code="provider_rejected", message=str(exc), exception=exc)
    return None
