import pytest

from app.data.mapping import (
    Market,
    pykrx_index_code,
    kis_index_code,
    market_from_pykrx_index,
    market_from_kis_index,
    normalize_ticker,
)


def test_pykrx_index_codes():
    assert pykrx_index_code(Market.KOSPI) == "1001"
    assert pykrx_index_code(Market.KOSDAQ) == "2001"


def test_kis_index_codes():
    assert kis_index_code(Market.KOSPI) == "0001"
    assert kis_index_code(Market.KOSDAQ) == "1001"


def test_code_collision_is_absorbed():
    # 같은 문자열 "1001" 이 소스에 따라 다른 시장 — 충돌 흡수 증명
    assert market_from_pykrx_index("1001") == Market.KOSPI
    assert market_from_kis_index("1001") == Market.KOSDAQ


def test_kospi_identity_roundtrip():
    for m in (Market.KOSPI, Market.KOSDAQ):
        assert market_from_pykrx_index(pykrx_index_code(m)) == m
        assert market_from_kis_index(kis_index_code(m)) == m


def test_unknown_index_raises():
    with pytest.raises(KeyError):
        market_from_kis_index("9999")


def test_normalize_ticker_zero_pads_and_strips():
    assert normalize_ticker("660") == "000660"
    assert normalize_ticker("005930") == "005930"
    assert normalize_ticker(" 000660.KS ") == "000660"
    assert normalize_ticker(660) == "000660"
