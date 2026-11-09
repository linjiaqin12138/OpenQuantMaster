from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def parse_iso_to_ms(value: str | None) -> int | None:
    """Parse an ISO-8601 timestamp into epoch milliseconds (UTC)."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def parse_iso_to_utc(value: str, *, default_tz: ZoneInfo | None = None) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime.

    Naive timestamps are read in ``default_tz`` when given, otherwise in UTC.
    """
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz or timezone.utc)
    return parsed.astimezone(timezone.utc)


def format_utc_iso(value: datetime) -> str:
    """Render an aware datetime as a ``Z`` suffixed UTC ISO-8601 string."""
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
