from __future__ import annotations

import re

A_SHARE_SUFFIXES = ("SH", "SZ", "BJ")

_A_SHARE_CODE = re.compile(r"^\d{6}$")
_A_SHARE_CODE_WITH_SUFFIX = re.compile(r"^\d{6}\.(SH|SZ|BJ)$")

_SHANGHAI_PREFIXES = "56"
_BEIJING_PREFIXES = "489"


def a_share_symbol_candidates(symbol: str) -> list[str]:
    """Return every A-share symbol that may carry ``symbol``, in query order.

    A code prefix never decides the exchange on its own: ``9`` covers both the
    Shanghai B shares and the Beijing codes, and ``1`` covers both Shenzhen
    funds and Shanghai convertible bonds. The prefix only orders the queries;
    the caller confirms the result against the data source and rejects a code
    that resolves to more than one listing.
    """
    code = symbol.strip().upper()
    if _A_SHARE_CODE_WITH_SUFFIX.match(code):
        return [code]
    if not _A_SHARE_CODE.match(code):
        return []
    return [f"{code}.{suffix}" for suffix in _suffix_order(code[0])]


def _suffix_order(prefix: str) -> tuple[str, ...]:
    if prefix in _SHANGHAI_PREFIXES:
        return ("SH", "SZ")
    if prefix in _BEIJING_PREFIXES:
        return ("BJ", "SH", "SZ")
    return ("SZ", "SH")
