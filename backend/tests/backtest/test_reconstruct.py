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


from app.backtest.reconstruct import rolling_high_excluding_current


def test_rolling_high_excludes_current_bar_spike():
    # 당일 t의 거대한 high 스파이크가 H_ref[t]에 절대 들어가면 안 된다(룩어헤드 금지)
    high = pd.Series([100.0, 110.0, 105.0, 999.0], index=pd.RangeIndex(4))
    href = rolling_high_excluding_current(high, window=3)
    # t=3 의 H_ref 는 [t-3..t-1] = [100,110,105] 의 max = 110 (999 제외)
    assert href.iloc[3] == 110.0
    # t=0 은 이전 데이터 없음 → NaN
    assert pd.isna(href.iloc[0])


def test_rolling_high_uses_only_prior_window():
    high = pd.Series([10.0, 20.0, 5.0, 7.0, 30.0])
    href = rolling_high_excluding_current(high, window=2)
    # t=2: max(high[0..1]) = 20 ;  t=4: max(high[2..3]) = 7
    assert href.iloc[2] == 20.0
    assert href.iloc[4] == 7.0
