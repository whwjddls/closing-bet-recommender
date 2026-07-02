from datetime import date, datetime

from app.store.models import Performance, Recommendation


def _rec(rid, run_date=date(2026, 6, 30), grade="S", ticker="000660",
         bpf=None, bpp=9.5, target=11.0, stop=9.0, rank=None):
    return Recommendation(id=rid, run_date=run_date, ticker=ticker, name=f"N{ticker}",
                          market="KOSPI", rank=rank if rank is not None else rid,
                          price_provisional=10.0, buy_price_provisional=bpp, buy_price_final=bpf,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=1.0,
                          veto=1, core=1.0, final=1.0, grade=grade, near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=target, stop_price=stop, spark=[1.0, 2.0], base_flag=False,
                          provisional_flag=True, created_at=datetime.now())


def _perf(rid, outcome="SUCCESS", vwap=10.6, eval_date=date(2026, 7, 1)):
    return Performance(rec_id=rid, eval_date=eval_date, buy_price_final=10.0,
                       vwap_0900_1000=vwap, morning_return=0.01, outcome=outcome,
                       dart_overnight_flag=False, scored_at=datetime.now())


def test_reminder_empty_when_no_recommendations(client):
    body = client.get("/reminder").json()
    assert body["picks"] == []


def test_reminder_returns_latest_run_picks_shape(client, db_session):
    # 이전 run_date 는 무시하고 최신(2026-06-30) 픽만 반환
    db_session.add(_rec(1, run_date=date(2026, 6, 29), ticker="005930"))
    db_session.add(_rec(2, run_date=date(2026, 6, 30), ticker="000660", bpf=9.8))
    db_session.commit()
    picks = client.get("/reminder").json()["picks"]
    assert len(picks) == 1
    p = picks[0]
    assert p["ticker"] == "000660"
    assert p["name"] == "N000660"
    assert p["grade"] == "S"
    assert p["target_price"] == 11.0
    assert p["stop_price"] == 9.0


def test_reminder_buy_price_prefers_final_then_provisional(client, db_session):
    db_session.add(_rec(1, run_date=date(2026, 6, 30), ticker="000660", bpf=9.8, bpp=9.5, rank=1))
    db_session.add(_rec(2, run_date=date(2026, 6, 30), ticker="005930", bpf=None, bpp=8.5, rank=2))
    db_session.commit()
    picks = {p["ticker"]: p for p in client.get("/reminder").json()["picks"]}
    assert picks["000660"]["buy_price"] == 9.8       # final 우선
    assert picks["005930"]["buy_price"] == 8.5       # final None → provisional


def test_reminder_outcome_and_vwap_null_when_unscored(client, db_session):
    db_session.add(_rec(1, run_date=date(2026, 6, 30), ticker="000660"))
    db_session.commit()
    p = client.get("/reminder").json()["picks"][0]
    assert p["outcome"] is None
    assert p["morning_vwap"] is None


def test_reminder_joins_performance_when_scored(client, db_session):
    db_session.add(_rec(1, run_date=date(2026, 6, 30), ticker="000660"))
    db_session.add(_perf(1, outcome="SUCCESS", vwap=10.6))
    db_session.commit()
    p = client.get("/reminder").json()["picks"][0]
    assert p["outcome"] == "SUCCESS"
    assert p["morning_vwap"] == 10.6
