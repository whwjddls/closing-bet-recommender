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


from app.backtest.reconstruct import point_in_time_universe


def _membership():
    # listing_date <= t < delisting_date 인 종목이 t 시점 유니버스
    return pd.DataFrame(
        {
            "ticker": ["000660", "005930", "900110", "111111"],
            "listing_date": ["2010-01-01", "2000-01-01", "2015-01-01", "2030-01-01"],
            "delisting_date": [pd.NaT, pd.NaT, "2026-09-01", pd.NaT],
        }
    )


def test_point_in_time_includes_later_delisted_ticker():
    # 900110 은 2026-09-01 상폐 → 2026-06-30 시점엔 '상장 중'이므로 포함되어야 한다
    # (오늘의 상장목록만 쓰면 누락 → 생존편향. 그 함정을 막는 테스트)
    uni = point_in_time_universe(_membership(), "2026-06-30")
    assert "900110" in uni
    assert {"000660", "005930"} <= uni


def test_point_in_time_excludes_not_yet_listed():
    uni = point_in_time_universe(_membership(), "2026-06-30")
    assert "111111" not in uni  # 2030 상장 → 아직 미상장


def test_point_in_time_excludes_already_delisted():
    uni = point_in_time_universe(_membership(), "2026-10-01")
    assert "900110" not in uni  # 2026-09-01 상폐 후


def test_point_in_time_missing_source_fails_closed():
    # 생존편향 소스 미확보 시 '오늘 목록' 폴백 금지 → fail-closed
    with pytest.raises(SurvivorshipSourceMissing):
        point_in_time_universe(None, "2026-06-30")
    with pytest.raises(SurvivorshipSourceMissing):
        point_in_time_universe(pd.DataFrame(columns=["ticker"]), "2026-06-30")
