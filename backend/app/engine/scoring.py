"""복합 점수 (MVP 곱셈형 — 실효 3축).

core  = s_신 × rvol_confirm × supply_tilt      # 레짐 독립 '품질' (등급 산정 기준)
final = core × regime_mult(0/0.5/1) × veto(0/1) # 게이팅·랭킹 기준
"""
from __future__ import annotations


def core_score(s_shin: float, rvol_confirm: float, supply_tilt: float) -> float:
    return s_shin * rvol_confirm * supply_tilt


def final_score(core: float, regime_mult: float, veto: int) -> float:
    return core * regime_mult * veto
