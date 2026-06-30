"""위생 가드 — 정적(장전 프리페치)·동적(라이브 후) 분리.

정적: 우선주/ETF/ETN/SPAC 제외, 20일 평균거래대금 ≥ 10억, 관리/경고/위험 제외, 상장 ≥ 120일.
동적: 과열(상한가/등락률≥+20%/VI)·15:20 거래정지 제외.
"""
from __future__ import annotations

MIN_AVG_VALUE_20D = 1_000_000_000   # 10억 (글로벌 유동성 바닥)
MIN_LISTING_DAYS = 120
OVERHEAT_CHANGE_PCT = 20.0
EXCLUDED_SEC_TYPES = frozenset({"PREFERRED", "ETF", "ETN", "SPAC"})


def passes_static(
    sec_type: str,
    avg_value_20d: float,
    is_managed: bool,
    is_warning: bool,
    is_caution: bool,
    listing_days: int,
) -> bool:
    if sec_type in EXCLUDED_SEC_TYPES:
        return False
    if avg_value_20d < MIN_AVG_VALUE_20D:
        return False
    if is_managed or is_warning or is_caution:
        return False
    if listing_days < MIN_LISTING_DAYS:
        return False
    return True


def is_overheated(day_change_pct: float, is_limit_up: bool, is_vi: bool) -> bool:
    return is_limit_up or is_vi or day_change_pct >= OVERHEAT_CHANGE_PCT


def passes_dynamic(
    day_change_pct: float,
    is_limit_up: bool,
    is_vi: bool,
    is_halted: bool,
) -> bool:
    if is_halted:
        return False
    if is_overheated(day_change_pct, is_limit_up, is_vi):
        return False
    return True
