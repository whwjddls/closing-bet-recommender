from datetime import date, datetime, time
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.store.models import Base, Run, Recommendation, RegimeSnapshot
from app.scheduler.calendar import TradingCalendar
from app.scheduler import daily_run


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _rec_row(rank, ticker, name, grade="S"):
    return SimpleNamespace(rank=rank, ticker=ticker, name=name, market="KOSPI",
                           price_provisional=24500.0, buy_price_provisional=24500.0,
                           s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03,
                           regime_mult=1.0, veto=1, core=1.12, final=1.12, grade=grade,
                           near_252=1.02, near_60=1.04, rvol=2.5, target_price=25200.0,
                           stop_price=23800.0, spark=[1.0, 2.0, 3.0], base_flag=True,
                           provisional_flag=True)


def _result(coverage=90.0, data_available=True, recs=None):
    regimes = {"KOSPI": SimpleNamespace(market="KOSPI", index_level=2700.0, ma5=2680.0,
                                        ma5_prev=2670.0, cond_a=True, cond_b=True, regime_mult=1.0)}
    return SimpleNamespace(run_date=date(2026, 6, 30), session_type="정규",
                           data_available=data_available, kis_coverage_pct=coverage,
                           recommendations=recs if recs is not None else [], regimes=regimes)


def _cal(early=None):
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close=early or {})


IN_WINDOW = datetime(2026, 6, 30, 15, 20)      # 정규 발행 창(15:15–15:30) 안


def test_daily_run_publishes_and_persists_top3(session_factory):
    captured_snapshot_at = {}
    notify_calls = []
    snap_calls = []
    recs = [_rec_row(1, "000660", "SK하이닉스"), _rec_row(2, "005930", "삼성전자", "A"),
            _rec_row(3, "035720", "카카오", "B"), _rec_row(4, "068270", "셀트리온", "C")]

    def fake_pipeline(run_date, snapshot_at):
        captured_snapshot_at["t"] = snapshot_at
        return _result(recs=recs)

    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=fake_pipeline, session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: snap_calls.append((d, p))),
        now=IN_WINDOW,
    )
    assert rc == "OK"
    # 스냅샷 시각 = 정규일 15:20 (15:20–15:30 창)
    assert captured_snapshot_at["t"] == datetime(2026, 6, 30, 15, 20)
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "OK" and run.board_published is True and run.kis_coverage_pct == 90.0
        saved = db.scalars(select(Recommendation).order_by(Recommendation.rank)).all()
        assert [r.ticker for r in saved] == ["000660", "005930", "035720", "068270"]
        assert db.scalars(select(RegimeSnapshot)).first().market == "KOSPI"
    # top3만 알림
    assert len(notify_calls) == 1
    msg = notify_calls[0][1]
    assert "셀트리온" not in msg and "SK하이닉스" in msg
    assert snap_calls and snap_calls[0][0] == date(2026, 6, 30)


def test_daily_run_unpublished_when_coverage_below_floor(session_factory):
    snap_calls = []
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: _result(coverage=65.0, recs=[_rec_row(1, "000660", "SK")]),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: snap_calls.append(d)),
        now=IN_WINDOW,
    )
    assert rc == "UNPUBLISHED"
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "UNPUBLISHED" and run.board_published is False
        assert "커버리지" in run.reason
        assert db.scalars(select(Recommendation)).all() == []   # 영속화 금지
    assert snap_calls == []                                      # 스냅샷 미작성


def test_daily_run_unpublished_when_kis_fully_down(session_factory):
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: _result(data_available=False, coverage=0.0),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
        now=IN_WINDOW,
    )
    assert rc == "UNPUBLISHED"
    with session_factory() as db:
        assert "미수신" in db.get(Run, date(2026, 6, 30)).reason


def test_daily_run_special_session_snapshot_minus_10(session_factory):
    cap = {}

    def fake_pipeline(d, s):
        cap["t"] = s
        return _result(coverage=80.0, recs=[_rec_row(1, "000660", "SK")])

    daily_run.run_daily(
        date(2026, 9, 29), calendar=_cal(early={date(2026, 9, 29): time(14, 0)}),
        run_pipeline=fake_pipeline,
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
        now=datetime(2026, 9, 29, 13, 50),          # 조기폐장 창(13:45–14:00) 안
    )
    assert cap["t"] == datetime(2026, 9, 29, 13, 50)            # 마감14:00 − 10분
    with session_factory() as db:
        assert db.get(Run, date(2026, 9, 29)).session_type == "특수"


def test_daily_run_skips_non_trading_day(session_factory):
    rc = daily_run.run_daily(
        date(2026, 7, 1), calendar=_cal(),
        run_pipeline=lambda d, s: (_ for _ in ()).throw(AssertionError("pipeline 호출 금지")),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
    )
    assert rc is None


# ── 발행 창 가드(15:15–15:30) — 창 밖 실행은 어떤 쓰기도 하지 않는다 ────────
def _boom(d, s):
    raise AssertionError("발행 창 밖에서는 파이프라인을 호출하면 안 된다")


@pytest.mark.parametrize("moment,why", [
    (datetime(2026, 6, 30, 14, 0), "장중 조기 실행 — 부분 누적거래량이 15:20 스냅샷을 오염"),
    (datetime(2026, 6, 30, 15, 14), "창 시작 1분 전"),
    (datetime(2026, 6, 30, 15, 31), "마감 후 — 동시호가 포함 종일 거래량으로 오염"),
    (datetime(2026, 6, 30, 20, 0), "장 마감 한참 후"),
])
def test_daily_run_blocks_outside_publish_window(session_factory, moment, why):
    snap_calls = []
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=_boom,                      # 호출되면 AssertionError
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: snap_calls.append(d)),
        now=moment,
    )
    assert rc == "OUTSIDE_WINDOW", why
    assert snap_calls == []                      # JSON 스냅샷 미작성
    with session_factory() as db:                # runs/recommendations 무기록
        assert db.get(Run, date(2026, 6, 30)) is None
        assert db.scalars(select(Recommendation)).all() == []


@pytest.mark.parametrize("moment", [
    datetime(2026, 6, 30, 15, 15),               # 창 시작(경계 포함)
    datetime(2026, 6, 30, 15, 18),               # 스케줄러 기동 시각
    datetime(2026, 6, 30, 15, 30),               # 마감(경계 포함)
])
def test_daily_run_allows_inside_publish_window(session_factory, moment):
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: _result(recs=[_rec_row(1, "000660", "SK하이닉스")]),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
        now=moment,
    )
    assert rc == "OK"


def test_daily_run_allow_outside_window_escape_hatch(session_factory):
    # 백필/디버깅 전용 탈출구 — 명시적으로 켤 때만 창 밖 실행 허용.
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: _result(recs=[_rec_row(1, "000660", "SK하이닉스")]),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
        now=datetime(2026, 6, 30, 20, 0), allow_outside_window=True,
    )
    assert rc == "OK"
