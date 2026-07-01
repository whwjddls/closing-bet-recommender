"""통합 배선 회귀 테스트 — 단위는 초록이지만 프로덕션 배선이 깨진 결함을 잡는다.

1) orchestrate_run 이 run_pipeline_fn 주입 없이 **실제** run_pipeline 을 구동하는지
   (실 StaticCandidate/LiveQuote 형상 어댑터로), spark/base_flag 포함 RecRow 를 채우는지.
2) daily_run 영속화 → FastAPI /recommendations 왕복이 500 없이 spark/base_flag 를 노출하는지.
"""
from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.engine.orchestrator import RecRow, RegimeInfo, RunResult, orchestrate_run
from app.engine.pipeline import LiveQuote, StaticCandidate
from app.main import create_app
from app.scheduler import daily_run
from app.scheduler.calendar import TradingCalendar
from app.store.db import get_db
from app.store.models import Base


# ── (1) orchestrate_run ↔ 실제 run_pipeline ─────────────────────────────
class _RealShapeAdapter:
    """엔진-대면 어댑터 표면을 실제 파이프라인 형상(StaticCandidate/LiveQuote)으로 구현."""

    def __init__(self):
        self._cand = StaticCandidate(
            ticker="000660", name="SK하이닉스", market="KOSDAQ", sec_type="COMMON",
            avg_value_20d=50_000_000_000.0, is_managed=False, is_warning=False,
            is_caution=False, listing_days=300, high_60=23500.0, high_252=24000.0,
            prev_high=24800.0, atr20=300.0, d1_supply_value=8_000_000_000.0,
            d1_value=50_000_000_000.0,
            recent_closes=(23000.0, 23500.0, 24000.0, 24500.0))
        self._quotes = {"000660": LiveQuote(
            p_now=24500.0, cum_volume_1520=2500.0, day_change_pct=3.0,
            is_limit_up=False, is_vi=False, is_halted=False)}

    def build_candidates(self, run_date, snapshot_at):
        return [self._cand]

    def fetch_live(self, tickers):
        return {t: self._quotes[t] for t in tickers if t in self._quotes}

    def regime_inputs(self, market):
        if market == "KOSDAQ":
            return (350.0, [349.0, 348.0, 347.0, 346.0, 345.0])   # UP 레짐
        return (2700.0, [2650.0, 2655.0, 2660.0, 2665.0, 2670.0])

    def dilution_veto(self, ticker, snapshot_at):
        return 1


class _DictStore:
    def __init__(self):
        self.vol = []
        self.regimes = []

    def upsert_volume_snapshot(self, ticker, run_date, cum_volume, cum_value):
        self.vol.append((ticker, run_date, cum_volume, cum_value))

    def trailing_volume(self, ticker, before):
        return []                                                 # cold start → modeled None

    def save_regime(self, run_date, market, info):
        self.regimes.append((market, info))


def test_orchestrate_run_with_real_pipeline():
    store = _DictStore()
    res = orchestrate_run(
        date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
        adapter=_RealShapeAdapter(), store=store)               # ← run_pipeline_fn 주입 없음

    assert isinstance(res, RunResult) and res.data_available is True
    assert set(res.regimes) == {"KOSPI", "KOSDAQ"}
    assert res.kis_coverage_pct == 100.0                        # pr.coverage_pct × 100
    assert res.recommendations, "실 파이프라인이 후보를 방출해야 한다"
    rec = res.recommendations[0]
    assert isinstance(rec, RecRow) and rec.ticker == "000660"
    # 실제 EngineRow attr 매핑 (price_provisional/buy/target/stop)
    assert rec.price_provisional == 24500.0
    assert rec.buy_price_provisional == 24500.0
    assert rec.target_price > 0 and rec.stop_price > 0
    # spark/base_flag 가 엔드투엔드로 실려야 한다
    assert rec.spark == [0.9388, 0.9592, 0.9796, 1.0]
    assert isinstance(rec.base_flag, bool) and rec.base_flag is True
    # RVOL 생산자: 스냅샷 upsert 발생 (cum_value 없이도)
    assert store.vol and store.vol[0][2] == 2500.0


# ── (2) daily_run 영속화 → /recommendations 왕복 ─────────────────────────
def _rec_row(rank, ticker, name):
    return RecRow(
        rank=rank, ticker=ticker, name=name, market="KOSPI",
        price_provisional=24500.0, buy_price_provisional=24500.0, buy_price_final=None,
        target_price=25200.0, stop_price=23800.0, s_shin=1.16, s_geo=0.83,
        rvol_confirm=0.93, supply_tilt=1.03, regime_mult=1.0, veto=1, core=1.12,
        final=1.12, grade="S", near_252=1.02, near_60=1.04, rvol=2.5,
        spark=[1.0, 2.0, 3.0], base_flag=True)


def test_daily_run_to_recommendations_roundtrip():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    run_date = date(2026, 6, 30)

    regimes = {"KOSPI": RegimeInfo(market="KOSPI", index_level=2700.0, ma5=2680.0,
                                   regime_mult=1.0, cond_a=True, cond_b=True)}
    result = RunResult(run_date=run_date, session_type="정규", data_available=True,
                       kis_coverage_pct=90.0,
                       recommendations=[_rec_row(1, "000660", "SK하이닉스")],
                       regimes=regimes)

    rc = daily_run.run_daily(
        run_date, calendar=TradingCalendar(holidays=set(), early_close={}),
        run_pipeline=lambda d, s: result, session_factory=factory,
        notify=lambda t, m: None,
        snapshots=type("S", (), {"write_snapshot": staticmethod(lambda d, p: None)})())
    assert rc == "OK"

    app = create_app()

    def _override():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    resp = client.get("/recommendations/2026-06-30")
    assert resp.status_code == 200                              # 500 아님
    body = resp.json()
    row = body["recommendations"][0]
    assert row["spark"] == [1.0, 2.0, 3.0]                      # spark 엔드투엔드
    assert row["base_flag"] is True                            # base_flag 엔드투엔드 (required bool)
