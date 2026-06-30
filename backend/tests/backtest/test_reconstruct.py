import pandas as pd
import pytest

from app.backtest.reconstruct import (
    LookaheadError,
    SurvivorshipSourceMissing,
    guard_final_dates,
)


def test_guard_final_dates_passes_when_all_strictly_before_as_of():
    # as_of=t(2026-06-30) FINAL 입력은 모두 t-1 이전이어야 한다
    guard_final_dates("2026-06-30", ["2026-06-26", "2026-06-29"], label="FINAL")


def test_guard_final_dates_rejects_same_day_data():
    # 당일(t) 데이터가 FINAL 경로에 섞이면 룩어헤드 → 실패
    with pytest.raises(LookaheadError):
        guard_final_dates("2026-06-30", ["2026-06-29", "2026-06-30"], label="FINAL")


def test_guard_final_dates_rejects_future_data():
    with pytest.raises(LookaheadError):
        guard_final_dates("2026-06-30", ["2026-07-01"], label="FINAL")


def test_survivorship_source_missing_is_an_exception():
    assert issubclass(SurvivorshipSourceMissing, Exception)
