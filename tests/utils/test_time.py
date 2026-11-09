from datetime import datetime, timezone

import pytest

from src.utils.time import format_utc_iso, parse_iso_to_ms, parse_iso_to_utc


@pytest.mark.unit
def test_parse_iso_to_ms_reads_utc_timestamps():
    assert parse_iso_to_ms("2026-01-01T00:00:00Z") == 1767225600000


@pytest.mark.unit
def test_parse_iso_to_ms_reads_naive_timestamps_as_utc():
    assert parse_iso_to_ms("2026-01-01T00:00:00") == 1767225600000


@pytest.mark.unit
def test_parse_iso_to_ms_passes_none_through():
    assert parse_iso_to_ms(None) is None


@pytest.mark.unit
def test_parse_iso_to_utc_converts_to_utc():
    parsed = parse_iso_to_utc("2026-01-01T00:00:00Z")

    assert parsed == datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.unit
def test_parse_iso_to_utc_uses_the_default_timezone():
    from zoneinfo import ZoneInfo

    parsed = parse_iso_to_utc(
        "2026-01-02 03:04:05",
        default_tz=ZoneInfo("Asia/Shanghai"),
    )

    assert format_utc_iso(parsed) == "2026-01-01T19:04:05Z"
