from datetime import date, datetime, time
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.store.models import Base, Recommendation, Performance
from app.scheduler.calendar import TradingCalendar
from app.scheduler import scoring_job


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _rec(db, rid, ticker, run_date=date(2026, 6, 29)):
    db.add(Recommendation(id=rid, run_date=run_date, ticker=ticker, name=f"N{ticker}", market="KOSPI",
                          rank=rid, price_provisional=10.0, buy_price_provisional=10.0, buy_price_final=None,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=1.0, veto=1,
                          core=1.0, final=1.0, grade="S", near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=11.0, stop_price=9.0, provisional_flag=True, created_at=datetime.now()))


def _cal():
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close={})


def test_scoring_marks_success_fail_and_na(session_factory):
    with session_factory() as db:
        _rec(db, 1, "AAA"); _rec(db, 2, "BBB"); _rec(db, 3, "CCC")
        db.commit()

    closes = {"AAA": 10.0, "BBB": 10.0, "CCC": 10.0}
    vwaps = {"AAA": 10.6, "BBB": 9.95, "CCC": None}    # CCC: 잠김 → NA
    dart = {"BBB"}

    scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory,
        fetch_confirmed_close=lambda t, d: closes[t],
        fetch_morning_vwap=lambda t, d: vwaps[t],
        overnight_scan=lambda t, since, until: t in dart,
    )
    with session_factory() as db:
        perfs = {p.rec_id: p for p in db.scalars(select(Performance)).all()}
        assert perfs[1].outcome == "SUCCESS" and perfs[1].morning_return > 0
        assert perfs[2].outcome == "FAIL" and perfs[2].dart_overnight_flag is True
        assert perfs[3].outcome == "NA" and perfs[3].morning_return is None
        # 확정 종가가 buy_price_final로 반영
        assert db.get(Recommendation, 1).buy_price_final == 10.0


def test_scoring_no_lookahead_uses_t_for_close_and_t_plus_1_for_vwap(session_factory):
    with session_factory() as db:
        _rec(db, 1, "AAA", run_date=date(2026, 6, 29))
        db.commit()
    close_args, vwap_args = [], []
    scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory,
        fetch_confirmed_close=lambda t, d: close_args.append(d) or 10.0,
        fetch_morning_vwap=lambda t, d: vwap_args.append(d) or 10.5,
        overnight_scan=lambda t, s, u: False,
    )
    assert close_args == [date(2026, 6, 29)]    # close[t]
    assert vwap_args == [date(2026, 6, 30)]     # VWAP[t+1]
    assert close_args[0] < vwap_args[0]          # 룩어헤드 없음


def test_scoring_binds_real_module_collaborators_without_import_error(session_factory):
    # 실제 기본 바인딩(NO 주입/NO override): fetch_confirmed_close/fetch_morning_vwap/
    # overnight_scan 을 실 모듈 함수로 지연 바인딩한다. 추천 0건 거래일이라 네트워크
    # 호출 없이 ImportError 없이 0건 채점되어야 한다(모듈 정본 함수 미존재 회귀 방지).
    scored = scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory)
    assert scored == 0


def test_scoring_is_idempotent(session_factory):
    with session_factory() as db:
        _rec(db, 1, "AAA"); db.commit()
    kw = dict(calendar=_cal(), session_factory=session_factory,
              fetch_confirmed_close=lambda t, d: 10.0, fetch_morning_vwap=lambda t, d: 10.5,
              overnight_scan=lambda t, s, u: False)
    scoring_job.run_scoring(date(2026, 6, 30), **kw)
    scoring_job.run_scoring(date(2026, 6, 30), **kw)   # 재실행
    with session_factory() as db:
        assert len(db.scalars(select(Performance)).all()) == 1   # 중복 채점 금지
