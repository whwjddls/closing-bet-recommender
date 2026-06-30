from __future__ import annotations

import re
from enum import Enum

_DIGITS = re.compile(r"\d+")


class Market(str, Enum):
    KOSPI = "KOSPI"
    KOSDAQ = "KOSDAQ"


# 아키텍처 §1 인덱스 코드 매핑 (충돌 주의)
_PYKRX_INDEX: dict[Market, str] = {Market.KOSPI: "1001", Market.KOSDAQ: "2001"}
_KIS_INDEX: dict[Market, str] = {Market.KOSPI: "0001", Market.KOSDAQ: "1001"}

_PYKRX_INDEX_REV: dict[str, Market] = {v: k for k, v in _PYKRX_INDEX.items()}
_KIS_INDEX_REV: dict[str, Market] = {v: k for k, v in _KIS_INDEX.items()}


def pykrx_index_code(market: Market) -> str:
    return _PYKRX_INDEX[market]


def kis_index_code(market: Market) -> str:
    return _KIS_INDEX[market]


def market_from_pykrx_index(code: str) -> Market:
    return _PYKRX_INDEX_REV[code]


def market_from_kis_index(code: str) -> Market:
    return _KIS_INDEX_REV[code]


def pykrx_market_name(market: Market) -> str:
    return market.value  # pykrx는 "KOSPI"/"KOSDAQ" 문자열 사용


def normalize_ticker(raw) -> str:
    """6자리 제로패딩 표준 티커. '660'→'000660', '000660.KS'→'000660'."""
    match = _DIGITS.search(str(raw))
    if not match:
        raise ValueError(f"no digits in ticker: {raw!r}")
    return match.group(0).zfill(6)
