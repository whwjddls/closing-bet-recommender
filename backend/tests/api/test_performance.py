from datetime import date, datetime

import pytest

from app.api.performance import (
    classify_fail_reason,
    compute_max_consec_loss_days,
    compute_mdd,
    compute_payoff_ratio,
    get_benchmark_provider,
    wilson_ci,
)
from app.store.models import Performance, Recommendation


def _rec(rid, grade="S", regime=1.0, ticker="000660"):
    return Recommendation(id=rid, run_date=date(2026, 6, 29), ticker=ticker, name=f"N{ticker}", market="KOSPI",
                          rank=rid, price_provisional=1.0, buy_price_provisional=1.0, buy_price_final=None,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=regime,
                          veto=1, core=1.0, final=1.0, grade=grade, near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=1.1, stop_price=0.9, spark=[1.0, 2.0], base_flag=False,
                          provisional_flag=True, created_at=datetime.now())


def _perf(rid, outcome, ret, vwap=10.0, flag=False, bpf=10.0, eval_date=date(2026, 6, 30)):
    return Performance(rec_id=rid, eval_date=eval_date, buy_price_final=bpf,
                       vwap_0900_0920=vwap, vwap_0900_1000=vwap, morning_return=ret,
                       outcome=outcome, dart_overnight_flag=flag, scored_at=datetime.now())


def test_performance_aggregate_arrays_and_excludes_na(client, db_session):
    db_session.add_all([_rec(1, "S", 1.0, "000660"), _rec(2, "A", 1.0, "005930"), _rec(3, "B", 0.5, "035720")])
    db_session.add_all([
        _perf(1, "SUCCESS", 0.0053, vwap=10.6),
        _perf(2, "FAIL", -0.004, vwap=9.96),
        _perf(3, "NA", None, vwap=None, flag=True),   # 잠김 → 분모 제외
    ])
    db_session.commit()
    body = client.get("/performance").json()
    assert body["eval_date"] == "2026-06-30"
    agg = body["aggregate"]
    assert agg["sample_size"] == 2                # NA 제외
    assert abs(agg["hit_rate"] - 0.5) < 1e-9
    assert agg["cold_start"] is True              # sample_size < 30
    # 00 §5: by_grade/by_regime/cumulative_curve 는 배열(ARRAY)
    assert isinstance(agg["by_grade"], list)
    assert isinstance(agg["by_regime"], list)
    assert isinstance(agg["cumulative_curve"], list)
    grades = {b["grade"]: b for b in agg["by_grade"]}
    assert grades["S"]["hit_rate"] == 1.0 and grades["S"]["n"] == 1
    assert grades["A"]["hit_rate"] == 0.0 and grades["A"]["n"] == 1
    regimes = {b["regime"]: b for b in agg["by_regime"]}
    assert regimes["1.0"]["n"] == 2              # 채점된 2건 모두 regime 1.0
    assert "0.5" not in regimes                  # NA뿐인 레짐 → 분모0 → 버킷 없음
    assert all(("date" in p and "cum" in p) for p in agg["cumulative_curve"])
    picks = {p["ticker"]: p for p in body["picks"]}
    assert picks["035720"]["outcome"] == "NA"
    assert picks["035720"]["dart_overnight_flag"] is True


def test_performance_empty(client):
    body = client.get("/performance").json()
    agg = body["aggregate"]
    assert agg["sample_size"] == 0
    assert agg["cold_start"] is True
    assert agg["by_grade"] == [] and agg["by_regime"] == []
    assert agg["cumulative_curve"] == []
    assert body["picks"] == []


# ── S1 성과추적 강화: 순수 함수 단위 검증 ──────────────────────────────
def test_wilson_ci_bounds_and_known_value():
    low, high = wilson_ci(8, 10)
    assert 0.0 <= low <= high <= 1.0
    assert low == pytest.approx(0.4902, abs=1e-3)
    assert high == pytest.approx(0.9434, abs=1e-3)


def test_wilson_ci_empty_sample_is_zero_zero():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_compute_mdd_peak_to_trough():
    # 누적곡선 [0.02,-0.01,-0.02,0.02] → 최대낙폭 0.03-(-0.02)=0.04
    assert compute_mdd([0.02, -0.01, -0.02, 0.02]) == pytest.approx(0.04)


def test_compute_mdd_empty_is_zero():
    assert compute_mdd([]) == 0.0


def test_compute_payoff_ratio_profit_over_loss():
    # 이익 [0.02,0.04] 평균 0.03 / 손실 [-0.03,-0.01] 절대평균 0.02 = 1.5
    assert compute_payoff_ratio([0.02, -0.03, -0.01, 0.04]) == pytest.approx(1.5)


def test_compute_payoff_ratio_zero_when_no_losses():
    assert compute_payoff_ratio([0.02, 0.04]) == 0.0


def test_compute_max_consec_loss_days_counts_run():
    # 일별 합 [+, -, -, +] → 최대 연속 손실일 2
    daily = {date(2026, 6, 29): 0.02, date(2026, 6, 30): -0.03,
             date(2026, 7, 1): -0.01, date(2026, 7, 2): 0.04}
    assert compute_max_consec_loss_days(daily) == 2


def test_classify_fail_reason():
    assert classify_fail_reason("FAIL", -0.05) == "갭하락"       # < -0.02
    assert classify_fail_reason("FAIL", -0.01) == "장중반전"     # >= -0.02
    assert classify_fail_reason("SUCCESS", -0.05) is None        # 비-FAIL → None
    assert classify_fail_reason("NA", None) is None


def test_performance_new_aggregate_metrics_and_fail_reason(client, db_session):
    db_session.add_all([_rec(1, "S", 1.0, "000660"), _rec(2, "S", 1.0, "005930"),
                        _rec(3, "S", 1.0, "035720"), _rec(4, "S", 1.0, "091990")])
    db_session.add_all([
        _perf(1, "SUCCESS", 0.02, eval_date=date(2026, 6, 29)),
        _perf(2, "FAIL", -0.03, eval_date=date(2026, 6, 30)),   # 갭하락(< -0.02)
        _perf(3, "FAIL", -0.01, eval_date=date(2026, 7, 1)),    # 장중반전
        _perf(4, "SUCCESS", 0.04, eval_date=date(2026, 7, 2)),
    ])
    db_session.commit()
    agg = client.get("/performance").json()["aggregate"]
    assert agg["mdd"] == pytest.approx(0.04)
    assert agg["payoff_ratio"] == pytest.approx(1.5)
    assert agg["max_consec_losses"] == 2
    picks = {p["ticker"]: p for p in client.get("/performance").json()["picks"]}
    assert picks["005930"]["fail_reason"] == "갭하락"
    assert picks["035720"]["fail_reason"] == "장중반전"
    assert picks["000660"]["fail_reason"] is None                # SUCCESS


def test_performance_buckets_include_wilson_ci(client, db_session):
    db_session.add_all([_rec(1, "S", 1.0, "000660"), _rec(2, "S", 1.0, "005930")])
    db_session.add_all([_perf(1, "SUCCESS", 0.01), _perf(2, "FAIL", -0.01)])
    db_session.commit()
    agg = client.get("/performance").json()["aggregate"]
    g = agg["by_grade"][0]
    assert 0.0 <= g["ci_low"] <= g["hit_rate"] <= g["ci_high"] <= 1.0
    r = agg["by_regime"][0]
    assert 0.0 <= r["ci_low"] <= r["hit_rate"] <= r["ci_high"] <= 1.0


def _fake_benchmark(start, end):
    return [{"date": "2026-06-29", "cum": 0.0}, {"date": "2026-06-30", "cum": 0.011}]


def test_performance_benchmark_curve_from_provider(client, db_session):
    client.app.dependency_overrides[get_benchmark_provider] = lambda: _fake_benchmark
    db_session.add(_rec(1, "S", 1.0, "000660"))
    db_session.add(_perf(1, "SUCCESS", 0.01, eval_date=date(2026, 6, 30)))
    db_session.commit()
    agg = client.get("/performance").json()["aggregate"]
    assert agg["benchmark_curve"] == [{"date": "2026-06-29", "cum": 0.0},
                                      {"date": "2026-06-30", "cum": 0.011}]


def test_performance_benchmark_curve_empty_when_unavailable(client, db_session):
    client.app.dependency_overrides[get_benchmark_provider] = \
        lambda: (lambda start, end: [])
    db_session.add(_rec(1, "S", 1.0, "000660"))
    db_session.add(_perf(1, "SUCCESS", 0.01, eval_date=date(2026, 6, 30)))
    db_session.commit()
    agg = client.get("/performance").json()["aggregate"]
    assert agg["benchmark_curve"] == []


def test_performance_na_missing_close_serializes_null_not_500(client, db_session):
    # 수정(c) 로 확정종가 결측(NA) 행은 buy_price_final=None 으로 영속됨 → /performance 가 500 나면 안 됨(#1)
    db_session.add(_rec(1, "S", 1.0, "000660"))
    db_session.add(_perf(1, "NA", None, vwap=None, bpf=None))
    db_session.commit()
    resp = client.get("/performance")
    assert resp.status_code == 200
    pick = resp.json()["picks"][0]
    assert pick["outcome"] == "NA"
    assert pick["buy_price_final"] is None
