"""등급 — core(레짐 독립) 기준 컷오프. S≥0.8 / A≥0.6 / B≥0.4 / C>0.

계약(00 §3): 엔진 공개 시그니처는 ``grade_of(core)``.
"""
from __future__ import annotations

from typing import Optional

GRADE_S = 0.8
GRADE_A = 0.6
GRADE_B = 0.4


def grade_of(core: float) -> Optional[str]:
    if core >= GRADE_S:
        return "S"
    if core >= GRADE_A:
        return "A"
    if core >= GRADE_B:
        return "B"
    if core > 0:
        return "C"
    return None
