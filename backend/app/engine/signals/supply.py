"""수급 — 외인·기관 D-1 확정치 양방향 틸트.

z           = clip((외인+기관 D-1 순매수액) / 20일 평균거래대금, -1, 1)
supply_tilt = clip(1.0 + 0.2·z, 0.8, 1.2)   # D-1 순매도는 1.0 미만 패널티
"""
from __future__ import annotations

Z_CLIP = 1.0
TILT_BASE = 1.0
TILT_SLOPE = 0.2
TILT_LOW = 0.8
TILT_HIGH = 1.2


def _clip(x: float, low: float, high: float) -> float:
    return max(low, min(x, high))


def supply_z(net_value_d1: float, avg_value_20d: float) -> float:
    if avg_value_20d <= 0:
        return 0.0
    return _clip(net_value_d1 / avg_value_20d, -Z_CLIP, Z_CLIP)


def supply_tilt(z: float) -> float:
    return _clip(TILT_BASE + TILT_SLOPE * z, TILT_LOW, TILT_HIGH)
