from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.store.models import Base, Run
from app.scheduler.calendar import TradingCalendar
from app.scheduler import premarket


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _cal():
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close={})


def test_premarket_blocks_and_skips_prefetch_when_health_fails(session_factory):
    prefetch_calls = []
    notify_calls = []
    report = SimpleNamespace(ok=False, latest_trading_day=date(2026, 6, 26), rows=0, detail="pykrx stale")

    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
    )
    assert rc == "BLOCKED"
    assert prefetch_calls == []                       # fail-closed: prefetch 미실행
    assert notify_calls and "stale" in notify_calls[0][1]
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "BLOCKED"
        assert run.board_published is False


def test_premarket_blocks_when_d1_supply_missing(session_factory):
    # 00 §2: health_check() 는 지수 OHLCV뿐 아니라 D-1 외인/기관 수급·거래대금 조회 성공도 검증한다.
    # 수급 결손 → ok=False → fail-closed(BLOCKED·prefetch 미실행).
    prefetch_calls = []
    notify_calls = []
    report = SimpleNamespace(ok=False, latest_trading_day=date(2026, 6, 26), rows=0,
                             detail="D-1 외인/기관 수급 결손")
    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
    )
    assert rc == "BLOCKED"
    assert prefetch_calls == []                        # 수급 결손 → prefetch 미실행
    assert notify_calls and "수급" in notify_calls[0][1]
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "BLOCKED" and run.board_published is False
        assert "수급" in run.reason


def test_premarket_prefetches_when_health_ok(session_factory):
    prefetch_calls = []
    report = SimpleNamespace(ok=True, latest_trading_day=date(2026, 6, 29), rows=2700, detail="ok")
    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: None,
    )
    assert rc == "OK"
    assert prefetch_calls == [date(2026, 6, 30)]


def test_premarket_skips_non_trading_day(session_factory):
    rc = premarket.run_premarket(
        date(2026, 7, 1), calendar=_cal(),
        health_check=lambda: (_ for _ in ()).throw(AssertionError("health 호출 금지")),
        prefetch_final=lambda d: None, session_factory=session_factory, notify=lambda t, m: None,
    )
    assert rc is None
