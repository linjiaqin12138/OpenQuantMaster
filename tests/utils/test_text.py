import pytest

from src.utils.text import collapse_whitespace, normalize_text


@pytest.mark.unit
def test_collapse_whitespace_replaces_runs_of_whitespace():
    assert collapse_whitespace("  a \n b\t c ") == "a b c"


@pytest.mark.unit
def test_normalize_text_casefolds_and_collapses():
    assert normalize_text("  News   About 降息 ") == "news about 降息"
