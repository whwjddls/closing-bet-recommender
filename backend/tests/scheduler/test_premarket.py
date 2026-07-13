from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.store.models import Base, Run, UniverseCache
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
        refresh_corp_map=lambda db: 3900,
    )
    assert rc == "OK"
    assert prefetch_calls == [date(2026, 6, 30)]


def test_premarket_blocks_when_corp_map_empty(session_factory):
    # corp_code_map 이 비면 전 종목 veto=0(fail-closed) → 보드 영구 공백이므로
    # 시딩 후에도 매핑 0 이면 prefetch 없이 차단(BLOCKED)해야 한다.
    prefetch_calls = []
    notify_calls = []
    report = SimpleNamespace(ok=True, latest_trading_day=date(2026, 6, 29), rows=2700, detail="ok")
    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
        refresh_corp_map=lambda db: 0,
    )
    assert rc == "BLOCKED"
    assert prefetch_calls == []                       # fail-closed: prefetch 미실행
    assert notify_calls and "corp_code_map" in notify_calls[0][1]
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "BLOCKED" and run.board_published is False
        assert "corp_code_map" in run.reason


def test_premarket_persists_final_bundle_when_health_ok(session_factory):
    # 00 §2: 헬스체크 통과 시 prefetch_final 이 산출한 FINAL 번들
    # (H_ref_252/H_ref_60/ATR20/avg_value_20d/D-1 수급)을 FINAL 캐시에 영속화하고
    # orchestrate_run 이 로드할 수 있어야 한다(번들 폐기 회귀 방지).
    from app.data.pykrx_client import PrefetchBundle
    from app.store import final_cache

    bundle = PrefetchBundle(
        run_date=date(2026, 6, 30), universe=["000660", "035720"],
        h_ref_252={"000660": 24000.0}, h_ref_60={"000660": 23500.0},
        atr20={"000660": 300.0}, avg_value_20d={"000660": 5e10},
        net_purchases={"000660": 8e9}, index_ma5={"KOSPI": 2700.0})
    report = SimpleNamespace(ok=True, latest_trading_day=date(2026, 6, 29),
                             rows=2700, detail="ok")

    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: bundle,
        session_factory=session_factory, notify=lambda t, m: None,
        name_bulk=lambda frm, to: {"000660": "SK하이닉스"},  # 벌크 종목명(오프라인)
        refresh_corp_map=lambda db: 3900)
    assert rc == "OK"

    with session_factory() as db:
        cached = final_cache.load_prefetch(db, date(2026, 6, 30))
        urow = db.get(UniverseCache, ("000660", date(2026, 6, 30)))
        assert urow is not None and urow.name == "SK하이닉스"  # 스캐너 종목명 채움
    assert set(cached) == {"000660"}                  # 정적위생 계산 성립 종목만
    row = cached["000660"]
    assert row.h_ref_252 == 24000.0
    assert row.h_ref_60 == 23500.0
    assert row.atr20 == 300.0
    assert row.avg_value_20d == 5e10
    assert row.d1_supply_value == 8e9                 # D-1 수급 결합


def test_premarket_success_clears_prior_block_record(session_factory):
    # 실패로 BLOCKED가 남은 뒤 같은 날 성공 재실행하면, stale BLOCKED 마커를 제거해야
    # /health가 이전 발행분으로 폴백한다(오탐 DEGRADED·수급결손 문구 잔존 방지).
    run_date = date(2026, 6, 30)
    premarket.run_premarket(                              # 1) 실패 → BLOCKED 기록
        run_date, calendar=_cal(),
        health_check=lambda: SimpleNamespace(ok=False, latest_trading_day=date(2026, 6, 26),
                                             rows=0, detail="D-1 외인/기관 수급 결손"),
        prefetch_final=lambda d: None,
        session_factory=session_factory, notify=lambda t, m: None)
    with session_factory() as db:
        assert db.get(Run, run_date).status == "BLOCKED"  # 전제 확인

    rc = premarket.run_premarket(                          # 2) 성공 재실행 → BLOCKED 제거
        run_date, calendar=_cal(),
        health_check=lambda: SimpleNamespace(ok=True, latest_trading_day=date(2026, 6, 29),
                                             rows=2700, detail="ok"),
        prefetch_final=lambda d: None,
        session_factory=session_factory, notify=lambda t, m: None,
        refresh_corp_map=lambda db: 3900)
    assert rc == "OK"
    with session_factory() as db:
        assert db.get(Run, run_date) is None              # stale BLOCKED 제거됨


def test_premarket_success_preserves_published_run(session_factory):
    # 이미 발행된(board_published=True) 기록은 성공 재실행이 지우지 않는다(스캔 결과 보존).
    run_date = date(2026, 6, 30)
    with session_factory() as db:
        db.add(Run(run_date=run_date, status="OK", board_published=True))
        db.commit()
    premarket.run_premarket(
        run_date, calendar=_cal(),
        health_check=lambda: SimpleNamespace(ok=True, latest_trading_day=date(2026, 6, 29),
                                             rows=2700, detail="ok"),
        prefetch_final=lambda d: None,
        session_factory=session_factory, notify=lambda t, m: None,
        refresh_corp_map=lambda db: 3900)
    with session_factory() as db:
        run = db.get(Run, run_date)
        assert run is not None and run.board_published is True


def test_premarket_skips_non_trading_day(session_factory):
    rc = premarket.run_premarket(
        date(2026, 7, 1), calendar=_cal(),
        health_check=lambda: (_ for _ in ()).throw(AssertionError("health 호출 금지")),
        prefetch_final=lambda d: None, session_factory=session_factory, notify=lambda t, m: None,
    )
    assert rc is None
