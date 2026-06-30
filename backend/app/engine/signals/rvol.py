"""거 — RVOL 확인 배수 (MODELED 분모·축적형).

RVOL         = 당일 15:20 누적거래량 / MODELED 15:20-시점 평균
s_거         = clip(log2(RVOL)/log2(3), 0, 1)
rvol_confirm = clip(0.6 + 0.4·s_거, 0.6, 1.0)   # 곱셈형 확인 배수(가산 아님)
분모 미축적(None) → 중립 1.0 (거 축 가중-언락 §3.2-C 보류). 빈약 거래량(데이터 有) → 0.6 할인.
"""
from __future__ import annotations

from math import log2
from typing import Optional

RVOL_LOG_BASE = 3.0
CONFIRM_FLOOR = 0.6
CONFIRM_SLOPE = 0.4
NEUTRAL_CONFIRM = 1.0


def _clip(x: float, low: float, high: float) -> float:
    return max(low, min(x, high))


def compute_rvol(cum_volume_1520: float, modeled_avg_1520: Optional[float]) -> Optional[float]:
    if modeled_avg_1520 is None or modeled_avg_1520 <= 0:
        return None
    return cum_volume_1520 / modeled_avg_1520


def s_geo(rvol: float) -> float:
    return _clip(log2(rvol) / log2(RVOL_LOG_BASE), 0.0, 1.0)


def rvol_confirm(rvol: Optional[float]) -> float:
    if rvol is None:
        return NEUTRAL_CONFIRM
    return _clip(CONFIRM_FLOOR + CONFIRM_SLOPE * s_geo(rvol), CONFIRM_FLOOR, NEUTRAL_CONFIRM)
