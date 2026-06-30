"""신 — 52주 신고가 근접도 + 돌파 마그니튜드 (s_신).

룩어헤드 금지: high_60/high_252 는 전일까지 확정 EOD 고가의 롤링 최대(당일 미포함).
term(n) = clip((n-0.90)/0.10,0,1) + 0.3·clip((n-1.00)/0.05,0,1)  # 돌파 캡 0.3 가산
s_신    = 0.7·term(near_252) + 0.3·term(near_60)
이력 120~251일: s_신 = term(near_60) (가중 1.0 재정규화), <120일 제외.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

NEAR_BASE = 0.90
NEAR_BASE_SPAN = 0.10
MAG_BASE = 1.00
MAG_SPAN = 0.05
MAG_CAP = 0.30
W_252 = 0.70
W_60 = 0.30
MIN_LISTING_DAYS = 120
FULL_HISTORY_DAYS = 252


def _clip(x: float, low: float, high: float) -> float:
    return max(low, min(x, high))


def term(near: float) -> float:
    base = _clip((near - NEAR_BASE) / NEAR_BASE_SPAN, 0.0, 1.0)
    magnitude = MAG_CAP * _clip((near - MAG_BASE) / MAG_SPAN, 0.0, 1.0)
    return base + magnitude


@dataclass(frozen=True)
class BreakoutResult:
    s_shin: float
    near_252: Optional[float]
    near_60: float
    label: str


def s_shin(
    p_now: float,
    high_60: float,
    high_252: Optional[float],
    listing_days: int,
) -> BreakoutResult:
    if listing_days < MIN_LISTING_DAYS:
        raise ValueError("listing_days < 120: excluded by hygiene before scoring")
    near_60 = p_now / high_60
    if listing_days >= FULL_HISTORY_DAYS and high_252 is not None:
        near_252 = p_now / high_252
        score = W_252 * term(near_252) + W_60 * term(near_60)
        return BreakoutResult(score, near_252, near_60, "52주 신고가")
    return BreakoutResult(term(near_60), None, near_60, "가용구간 고가")
