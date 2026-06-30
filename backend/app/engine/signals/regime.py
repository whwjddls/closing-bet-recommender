"""시황 — 지수 5일선 레짐 게이트 (4상태 MECE, HARD 게이트).

A = (지수 종가 ≥ 5일 이동평균)
B = (5일선 기울기 > 0; 오늘 5MA > 어제 5MA)
당일 등락률 C는 노이즈·중복 유발로 게이트에서 제외(결정론 확보).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

REGIME_UP = 1.0
REGIME_HALF = 0.5
REGIME_OFF = 0.0
MA5_WINDOW = 5


@dataclass(frozen=True)
class RegimeResult:
    cond_a: bool
    cond_b: bool
    ma5: float
    ma5_prev: float
    regime_mult: float


def classify_regime(cond_a: bool, cond_b: bool) -> float:
    if cond_a and cond_b:
        return REGIME_UP
    if cond_a and not cond_b:
        return REGIME_HALF
    if (not cond_a) and cond_b:
        return REGIME_HALF
    return REGIME_OFF


def compute_regime(index_level: float, prev5_closes: Sequence[float]) -> RegimeResult:
    """index_level=15:20 잠정 지수레벨, prev5_closes=[c_{t-1}..c_{t-5}] (최신순, FINAL)."""
    if len(prev5_closes) < MA5_WINDOW:
        raise ValueError("prev5_closes must contain 5 prior closes (t-1..t-5)")
    ma5 = (index_level + sum(prev5_closes[:4])) / MA5_WINDOW       # 오늘 5MA = 잠정 + 4 FINAL
    ma5_prev = sum(prev5_closes[:MA5_WINDOW]) / MA5_WINDOW         # 어제 5MA = t-1..t-5
    cond_a = index_level >= ma5
    cond_b = ma5 > ma5_prev
    return RegimeResult(cond_a, cond_b, ma5, ma5_prev, classify_regime(cond_a, cond_b))
