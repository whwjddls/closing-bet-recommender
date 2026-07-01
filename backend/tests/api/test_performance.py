from datetime import date, datetime

from app.store.models import Performance, Recommendation


def _rec(rid, grade="S", regime=1.0, ticker="000660"):
    return Recommendation(id=rid, run_date=date(2026, 6, 29), ticker=ticker, name=f"N{ticker}", market="KOSPI",
                          rank=rid, price_provisional=1.0, buy_price_provisional=1.0, buy_price_final=None,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=regime,
                          veto=1, core=1.0, final=1.0, grade=grade, near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=1.1, stop_price=0.9, spark=[1.0, 2.0], base_flag=False,
                          provisional_flag=True, created_at=datetime.now())


def _perf(rid, outcome, ret, vwap=10.0, flag=False, bpf=10.0):
    return Performance(rec_id=rid, eval_date=date(2026, 6, 30), buy_price_final=bpf,
                       vwap_0900_1000=vwap, morning_return=ret, outcome=outcome,
                       dart_overnight_flag=flag, scored_at=datetime.now())


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
