"""재 — DART 희석성 공시 매수 veto.

윈도우: T-1 15:20 < received_at ≤ T 15:20 (start 배타, end 포함; 룩어헤드 차단).
화이트리스트(희석성) substring 매칭만 veto=0 — "유상증자결정(정정)" 등 정정 변형 포착(계약 00 §2).
무상증자/주식배당 = non-dilutive → false-veto 금지.
corp_code↔티커 미매핑 → fail-closed(veto=0, 확인 불가 → 제외).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, Sequence

# 희석 화이트리스트(계약 00 §2) — substring 매칭으로 정정 변형까지 포착.
DILUTION_WHITELIST = frozenset({
    "유상증자결정",
    "전환사채권발행결정",
    "신주인수권부사채권발행결정",
    "교환사채권발행결정",
})
# non-dilutive(false-veto 금지) — 무상증자/주식배당은 우선 배제.
NON_DILUTIVE_EXCLUDED = frozenset({"무상증자결정", "주식배당"})
VETO_BLOCK = 0   # 매수 금지 (final=0)
VETO_PASS = 1


@dataclass(frozen=True)
class Disclosure:
    corp_code: str
    report_nm: str
    received_at: datetime


def _is_dilutive(report_nm: str) -> bool:
    # 무상증자/주식배당 false-veto 금지(우선 배제).
    if any(x in report_nm for x in NON_DILUTIVE_EXCLUDED):
        return False
    # substring 매칭 → "유상증자결정(정정)" 등 정정 변형도 포착.
    return any(key in report_nm for key in DILUTION_WHITELIST)


def in_window(received_at: datetime, window_start: datetime, window_end: datetime) -> bool:
    return window_start < received_at <= window_end


def compute_veto(
    ticker: str,
    ticker_to_corp: Mapping[str, str],
    disclosures: Sequence[Disclosure],
    window_start: datetime,
    window_end: datetime,
) -> int:
    corp_code = ticker_to_corp.get(ticker)
    if corp_code is None:
        return VETO_BLOCK  # fail-closed
    for d in disclosures:
        if d.corp_code != corp_code:
            continue
        if not _is_dilutive(d.report_nm):
            continue
        if in_window(d.received_at, window_start, window_end):
            return VETO_BLOCK
    return VETO_PASS
