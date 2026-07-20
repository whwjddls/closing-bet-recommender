"""MVP 엔지니어링 수용기준 — 보드 '완료' 정의(아키텍처 §5 발행 게이트)."""
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.data.kis_client import MorningVwap
from app.store.models import Base, Run, Recommendation
from app.scheduler.calendar import TradingCalendar
from app.scheduler import daily_run, scoring_job

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _cal(early=None):
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close=early or {})


# 게이트 1: 15:20–15:30 창 내 산출(정규=15:20, 특수=마감−10)
def test_gate_snapshot_within_window():
    cal = _cal(early={date(2026, 9, 29): time(14, 0)})
    snap = cal.snapshot_at(date(2026, 6, 30))
    assert time(15, 20) <= snap.time() < time(15, 30)
    assert cal.snapshot_at(date(2026, 9, 29)) == datetime(2026, 9, 29, 13, 50)


# 게이트 2: 커버리지 바닥(<70%) 미만이면 미발행
def test_gate_coverage_floor_blocks_publish(session_factory):
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: SimpleNamespace(
            run_date=d, session_type="정규", data_available=True, kis_coverage_pct=69.9,
            recommendations=[], regimes={}),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
        now=datetime(2026, 6, 30, 15, 20))          # 발행 창(15:15–15:30) 안
    assert rc == "UNPUBLISHED"
    with session_factory() as db:
        assert db.get(Run, date(2026, 6, 30)).board_published is False


# 게이트 3: 룩어헤드 가드(채점은 close[t]·VWAP[t+1])
def test_gate_scoring_lookahead_guard(session_factory):
    with session_factory() as db:
        db.add(Recommendation(id=1, run_date=date(2026, 6, 29), ticker="AAA", name="N", market="KOSPI",
                              rank=1, price_provisional=10.0, buy_price_provisional=10.0, buy_price_final=None,
                              s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=1.0,
                              veto=1, core=1.0, final=1.0, grade="S", near_252=1.0, near_60=1.0, rvol=2.0,
                              target_price=11.0, stop_price=9.0, provisional_flag=True, created_at=datetime.now()))
        db.commit()
    seen = {}
    scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory,
        fetch_confirmed_close=lambda t, d: seen.__setitem__("close", d) or 10.0,
        fetch_morning_vwaps=lambda t, d: seen.__setitem__("vwap", d) or MorningVwap(10.5, 10.5),
        overnight_scan=lambda t, s, u: False)
    assert seen["close"] == date(2026, 6, 29)   # t
    assert seen["vwap"] == date(2026, 6, 30)    # t+1 (미래 정보로 진입가 산정 안 함)


# 게이트 4: Windows 등록 스크립트가 3개 잡을 정의
def test_register_script_defines_three_jobs():
    text = (SCRIPTS / "register_tasks.ps1").read_text(encoding="utf-8")
    assert "app.scheduler.premarket" in text
    assert "app.scheduler.daily_run" in text
    assert "app.scheduler.scoring_job" in text
    assert "15:18" in text or "15:20" in text
