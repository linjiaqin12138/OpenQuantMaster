import pytest

from src.utils.symbols import a_share_symbol_candidates


@pytest.mark.unit
def test_a_known_suffix_is_kept_as_is():
    assert a_share_symbol_candidates("600519.SH") == ["600519.SH"]
    assert a_share_symbol_candidates("000300.sz") == ["000300.SZ"]


@pytest.mark.unit
def test_a_shanghai_code_is_queried_shanghai_first():
    assert a_share_symbol_candidates("600519") == ["600519.SH", "600519.SZ"]
    assert a_share_symbol_candidates("515070") == ["515070.SH", "515070.SZ"]


@pytest.mark.unit
def test_a_shenzhen_code_is_queried_shenzhen_first():
    assert a_share_symbol_candidates("000001") == ["000001.SZ", "000001.SH"]
    assert a_share_symbol_candidates("159915") == ["159915.SZ", "159915.SH"]


@pytest.mark.unit
def test_a_beijing_or_b_share_code_is_queried_beijing_first():
    assert a_share_symbol_candidates("430047") == [
        "430047.BJ",
        "430047.SH",
        "430047.SZ",
    ]
    assert a_share_symbol_candidates("900901") == [
        "900901.BJ",
        "900901.SH",
        "900901.SZ",
    ]


@pytest.mark.unit
def test_an_unsupported_symbol_has_no_candidate():
    assert a_share_symbol_candidates("AAPL") == []
    assert a_share_symbol_candidates("60051") == []
    assert a_share_symbol_candidates("") == []
