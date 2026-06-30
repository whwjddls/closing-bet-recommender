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


from app.backtest.reconstruct import reconstruct_pool, live_top30_only_rate


def _value_panel():
    rows = [
        ("2026-06-29", "A", 500.0),
        ("2026-06-29", "B", 500.0),  # A와 동점 → tie-break 티커 오름차순
        ("2026-06-29", "C", 900.0),
        ("2026-06-29", "D", 100.0),
        ("2026-06-26", "C", 10.0),   # 과거일은 무시(D-1=직전 거래일만)
        ("2026-06-30", "C", 9999.0), # 당일은 룩어헤드 → 무시
    ]
    return pd.DataFrame(rows, columns=["date", "ticker", "value"])


def test_reconstruct_pool_is_deterministic_and_tie_broken():
    universe = {"A", "B", "C", "D"}
    pool = reconstruct_pool(_value_panel(), "2026-06-30", universe, top_n=3)
    # value desc: C(900), A(500), B(500) → 동점은 ticker asc → A 먼저
    assert pool == ["C", "A", "B"]


def test_reconstruct_pool_is_invariant_to_row_order():
    universe = {"A", "B", "C", "D"}
    shuffled = _value_panel().sample(frac=1.0, random_state=7).reset_index(drop=True)
    assert reconstruct_pool(shuffled, "2026-06-30", universe, top_n=4) == \
           reconstruct_pool(_value_panel(), "2026-06-30", universe, top_n=4)


def test_reconstruct_pool_respects_universe_filter():
    pool = reconstruct_pool(_value_panel(), "2026-06-30", {"C", "D"}, top_n=10)
    assert pool == ["C", "D"]  # A,B 는 유니버스 밖


def test_live_top30_only_rate_quantifies_fresh_breakouts():
    # 라이브 top-30 단독발생(=D-1 풀 부재) 픽 비율 → 별도 paper-forward 검증 대상
    live_picks = ["C", "A", "X", "Y"]   # X,Y 는 D-1 풀에 없음
    d1_pool = ["C", "A", "B"]
    assert live_top30_only_rate(live_picks, d1_pool) == 0.5
    assert live_top30_only_rate([], d1_pool) == 0.0


from app.backtest.reconstruct import build_pnow_proxy


def test_pnow_proxy_equals_close_with_zero_haircut():
    # 인트라데이 이력 가능 구간 가정: haircut=0 → P_now ≈ close[t]
    p = build_pnow_proxy(10000.0, haircut=0.0, band=0.0)
    assert p["central"] == 10000.0
    assert p["low"] == 10000.0 and p["high"] == 10000.0


def test_pnow_proxy_applies_haircut_and_band():
    # close→15:20 드리프트를 haircut(중심) + band(민감도 밴드)로 정량화
    p = build_pnow_proxy(10000.0, haircut=0.01, band=0.005)
    assert p["central"] == pytest.approx(9900.0)
    assert p["low"] == pytest.approx(9900.0 * 0.995)
    assert p["high"] == pytest.approx(9900.0 * 1.005)
    # 밴드는 중심을 brackets
    assert p["low"] < p["central"] < p["high"]
