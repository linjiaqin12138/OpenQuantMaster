from __future__ import annotations


def collapse_whitespace(value: str) -> str:
    """Collapse runs of whitespace into single spaces."""
    return " ".join(value.split())


def normalize_text(value: str) -> str:
    """Casefolded, whitespace-collapsed text used for equality checks."""
    return collapse_whitespace(value).casefold()
