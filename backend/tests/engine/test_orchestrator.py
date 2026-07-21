from datetime import date, datetime
from types import SimpleNamespace

from app.engine.orchestrator import (
    orchestrate_run,
    RunResult,
    RecRow,
    compute_modeled_avg,
)
from app.engine.pipeline import LiveQuote, StaticCandidate


def _cand(ticker, market):
    return StaticCandidate(
        ticker=ticker, name=f"N{ticker}", market=market, sec_type="COMMON",
        avg_value_20d=5.0e8, is_managed=False, is_warning=False, is_caution=False,
        listing_days=300, high_60=95.0, high_252=98.0, prev_high=99.0, atr20=3.0,
        d1_supply_value=0.0, d1_value=5.0e10, recent_closes=(90.0, 95.0, 100.0))


class FakeAdapter:
    """엔진-대면 표면(build_candidates/fetch_live/regime_inputs/dilution_veto)."""

    def build_candidates(self, run_date, snapshot_at):
        # 풀 union: D-1 top ∪ 라이브 top (혼합시장)
        return [_cand("000660", "KOSDAQ"), _cand("005930", "KOSPI")]

    def fetch_live(self, tickers):
        return {t: LiveQuote(p_now=100.0, cum_volume_1520=1000.0, day_change_pct=1.0,
                             is_limit_up=False, is_vi=False, is_halted=False)
                for t in tickers}

    def regime_inputs(self, market):  # 둘 다 UP 레짐(regime_mult=1.0)
        return ((350.0, [349, 348, 347, 346, 345]) if market == "KOSDAQ"
                else (2700.0, [2650, 2655, 2660, 2665, 2670]))

    def dilution_veto(self, ticker, snapshot_at):
        return 0 if ticker == "000660" else 1        # 000660 희석 veto

    def dilution_veto_bulk(self, tickers, snapshot_at):
        return {t: self.dilution_veto(t, snapshot_at) for t in tickers}


class DictStore:                                     # 인메모리 store 페이크
    def __init__(self):
        self.vol = []
        self.regimes = []

    def upsert_volume_snapshot(self, ticker, d, cum_volume, cum_value):
        self.vol.append((ticker, d, cum_volume, cum_value))

    def trailing_volume(self, ticker, before):
        return []

    def save_regime(self, run_date, market, info):
        self.regimes.append((market, info))


def fake_run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg_by_ticker,
                      veto_by_ticker, max_emit):
    rows = []
    quotes = fetch_live([c.ticker for c in candidates])
    for c in candidates:
        if c.ticker not in quotes:
            continue
        if veto_by_ticker.get(c.ticker, 1) == 0:
            continue                                 # veto 탈락
        rm = regime_by_market[c.market]
        if rm == 0.0:
            continue                                 # 레짐 게이트
        rows.append(SimpleNamespace(
            rank=len(rows) + 1, ticker=c.ticker, name=c.name, market=c.market,
            price_provisional=100.0, buy_price_provisional=100.0, target_price=103.0,
            stop_price=97.0, s_shin=1.0, s_geo=0.8, rvol_confirm=0.9, supply_tilt=1.0,
            regime_mult=rm, veto=1, core=0.9, final=0.9 * rm, grade="A", near_252=1.0,
            near_60=1.0, rvol=2.0, spark=[0.9, 0.95, 1.0], base_flag=True))
    return SimpleNamespace(published=bool(rows), reason="OK", rows=rows, coverage_pct=1.0)


def test_orchestrate_pool_regime_coverage():
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=FakeAdapter(), store=DictStore(), run_pipeline_fn=fake_run_pipeline)
    assert isinstance(res, RunResult) and res.data_available is True
    emitted = {r.ticker for r in res.recommendations}
    assert "005930" in emitted and "000660" not in emitted           # 풀 union + veto 탈락
    assert res.kis_coverage_pct == 100.0                             # pr.coverage_pct ×100
    assert set(res.regimes) == {"KOSPI", "KOSDAQ"}                   # 시장별 RegimeInfo
    assert all(isinstance(r, RecRow) for r in res.recommendations)   # EngineRow→RecRow
    assert res.recommendations[0].spark == [0.9, 0.95, 1.0]          # spark 매핑
    assert res.recommendations[0].base_flag is True                 # base_flag 매핑


def test_modeled_rvol_threshold():
    assert compute_modeled_avg([1.0e8] * 19, min_sessions=20) is None     # <20세션 → 중립
    assert compute_modeled_avg([1.0e8] * 20, min_sessions=20) == 1.0e8    # ≥20세션 → 평균


def test_orchestrate_populates_real_ma5_prev_for_slope_audit():
    """cond_b(5MA 기울기) 감사를 위해 전일 5MA(ma5_prev)가 실제 계산·전파되어야 한다(None 금지).
    KOSPI 입력 prev5=[2650,2655,2660,2665,2670] → ma5_prev=(합)/5=2660.0."""
    store = DictStore()
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=FakeAdapter(), store=store, run_pipeline_fn=fake_run_pipeline)
    kospi = res.regimes["KOSPI"]
    assert kospi.ma5_prev is not None
    assert kospi.ma5_prev == 2660.0
    # store.save_regime 로 전파되어 RegimeSnapshot.ma5_prev 로 영속화 가능해야 한다
    saved = {market: info for market, info in store.regimes}
    assert saved["KOSPI"].ma5_prev == 2660.0


class PrefetchStore(DictStore):
    """장전 FINAL 캐시(load_prefetch)를 노출하는 store 페이크 (00 §2 재활용)."""

    def load_prefetch(self, run_date):
        return {"005930": SimpleNamespace(
            h_ref_252=111.0, h_ref_60=99.0, atr20=4.5,
            avg_value_20d=7.0e8, d1_supply_value=1.3e7)}


def test_orchestrate_loads_persisted_final_prefetch_into_candidates():
    """orchestrate_run 은 장전 영속화된 FINAL 번들(H_ref_252/H_ref_60/ATR20/
    avg_value_20d/D-1 순매수)을 로드해 StaticCandidate 필드를 채워야 한다(placeholder 금지)."""
    captured = {}

    def capturing_pipeline(candidates, fetch_live, regime_by_market, modeled_avg,
                           veto_by_ticker, max_emit):
        captured["candidates"] = list(candidates)
        return fake_run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg,
                                 veto_by_ticker, max_emit)

    orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                    adapter=FakeAdapter(), store=PrefetchStore(),
                    run_pipeline_fn=capturing_pipeline)

    by_ticker = {c.ticker: c for c in captured["candidates"]}
    overlaid = by_ticker["005930"]
    assert overlaid.high_252 == 111.0          # h_ref_252 → high_252
    assert overlaid.high_60 == 99.0            # h_ref_60 → high_60
    assert overlaid.atr20 == 4.5               # ATR20
    assert overlaid.avg_value_20d == 7.0e8     # 20일 평균거래대금
    assert overlaid.d1_supply_value == 1.3e7   # D-1 순매수
    # prefetch 에 없는 종목(000660)은 원본 후보값 유지
    assert by_ticker["000660"].high_252 == 98.0


class SignalAdapter(FakeAdapter):
    """T4 신호 배선 표면(VI/상한가/예상체결가/가집계/종목정보)을 노출하는 어댑터 페이크."""

    def __init__(self, *, vi=None, limit_up=None, exp=None, flows=None, ineligible=None):
        self._vi = vi or set()
        self._limit = limit_up or set()
        self._exp = exp or {}
        self._flows = flows or {}
        self._ineligible = ineligible or set()
        self.info_calls: list[str] = []

    def get_vi_tickers(self):
        return set(self._vi)

    def get_limit_up_tickers(self):
        return set(self._limit)

    def get_exp_closing_prices(self):
        return dict(self._exp)

    def get_provisional_flows(self):
        return dict(self._flows)

    def get_stock_basic_info(self, ticker):
        self.info_calls.append(ticker)
        return {"ticker": ticker, "is_ineligible": ticker in self._ineligible}


def _capture_quotes_pipeline(store_box):
    def pipeline(candidates, fetch_live, regime_by_market, modeled_avg, veto_by_ticker, max_emit):
        store_box["quotes"] = fetch_live([c.ticker for c in candidates])
        return fake_run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg,
                                 veto_by_ticker, max_emit)
    return pipeline


def test_orchestrate_dynamic_hygiene_marks_real_vi_limit_lists():
    """실제 VI/상한가 리스트 기반으로 후보 LiveQuote 플래그가 세팅돼야 한다(폴백과 OR)."""
    box = {}
    orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                    adapter=SignalAdapter(vi={"005930"}, limit_up={"000660"}),
                    store=DictStore(), run_pipeline_fn=_capture_quotes_pipeline(box))
    quotes = box["quotes"]
    assert quotes["005930"].is_vi is True          # VI 리스트 반영
    assert quotes["000660"].is_limit_up is True    # 상한가 리스트 반영


def test_orchestrate_fills_exp_close_and_supply_today():
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=SignalAdapter(exp={"005930": 71200.0},
                                                flows={"005930": "외인▲기관▲"}),
                          store=DictStore(), run_pipeline_fn=fake_run_pipeline)
    row = {r.ticker: r for r in res.recommendations}["005930"]
    assert row.exp_close == 71200.0
    assert row.supply_today == "외인▲기관▲"


def test_orchestrate_fills_none_when_signals_absent():
    """콜드/결측: 예상체결가·가집계 미제공이면 None(널-안전)."""
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=SignalAdapter(), store=DictStore(),
                          run_pipeline_fn=fake_run_pipeline)
    row = res.recommendations[0]
    assert row.exp_close is None and row.supply_today is None


def test_orchestrate_final_hygiene_excludes_ineligible_and_reranks():
    adapter = SignalAdapter(ineligible={"005930"})
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=adapter, store=DictStore(),
                          run_pipeline_fn=fake_run_pipeline)
    emitted = {r.ticker for r in res.recommendations}
    assert "005930" not in emitted                 # 부적격 → 최종 위생 제외
    assert adapter.info_calls == ["005930"]         # emit된 종목만 조회
    assert [r.rank for r in res.recommendations] == list(range(1, len(res.recommendations) + 1))


class CodeNamedAdapter(FakeAdapter):
    """프리페치 경로 증상 재현 — 후보 name 이 티커 그대로(이름원 없음)."""

    def build_candidates(self, run_date, snapshot_at):
        from dataclasses import replace

        return [replace(_cand("005930", "KOSPI"), name="005930")]


class NamesStore(DictStore):
    """universe_cache 종목명 맵(load_names)을 노출하는 store 페이크."""

    def load_names(self, run_date):
        return {"005930": "삼성전자"}


def test_orchestrate_overlays_universe_names_for_code_named_candidates():
    """name==ticker 후보는 store 의 universe_cache 이름으로 오버레이돼야 한다 —
    보드/리마인더/텔레그램에 종목명 대신 코드가 찍히는 UX 결함 방지."""
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=CodeNamedAdapter(), store=NamesStore(),
                          run_pipeline_fn=fake_run_pipeline)
    by = {r.ticker: r for r in res.recommendations}
    assert by["005930"].name == "삼성전자"


def test_orchestrator_store_load_names_latest_as_of_not_after_run_date():
    """실 OrchestratorStore.load_names — run_date 이하 최신 as_of 의 이름 맵.
    빈 이름/티커와 동일한 이름은 제외(오버레이 무의미)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.store.models import Base, UniverseCache
    from app.store.orchestrator_store import OrchestratorStore

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with Session() as db:
        db.add(UniverseCache(ticker="005930", as_of=date(2026, 6, 29), name="삼성전자(옛)"))
        db.add(UniverseCache(ticker="005930", as_of=date(2026, 6, 30), name="삼성전자"))
        db.add(UniverseCache(ticker="000660", as_of=date(2026, 6, 30), name="000660"))
        db.add(UniverseCache(ticker="035720", as_of=date(2026, 7, 2), name="카카오"))  # 미래 as_of
        db.commit()

    with Session() as db:
        names = OrchestratorStore(db).load_names(date(2026, 7, 1))
    assert names == {"005930": "삼성전자"}


# ── 정적위생 실배선: 15:20 병렬 기본정보(get_basic_info_bulk) → passes_static 반영 ──
def _basic_info_o(ticker, *, managed=False, warning=False, preferred=False):
    return {"ticker": ticker, "name": f"N{ticker}", "is_managed": managed,
            "is_warning": warning, "is_preferred": preferred,
            "is_ineligible": bool(managed or warning or preferred)}


def _clean_cand(ticker, market="KOSDAQ"):
    # 정적/동적/스코어 전부 통과해 실 run_pipeline 이 발행하는 후보(test_pipeline 파형)
    return StaticCandidate(
        ticker=ticker, name=f"N{ticker}", market=market, sec_type="COMMON",
        avg_value_20d=50_000_000_000.0, is_managed=False, is_warning=False,
        is_caution=False, listing_days=300, high_60=23500.0, high_252=24000.0,
        prev_high=24800.0, atr20=300.0, d1_supply_value=8_000_000_000.0,
        d1_value=50_000_000_000.0, recent_closes=(23000.0, 23500.0, 24000.0))


class HygieneAdapter(FakeAdapter):
    """15:20 병렬 기본정보(get_basic_info_bulk)를 노출 — 관리/경고/우선주 플래그원.

    build_candidates 는 4종목(우선주/관리/경고/정상)을 전부 '깨끗한(COMMON/False)' 상태로
    낸다 — 위생조회 반영 전엔 4종 모두 발행되고, 반영 후 부적격 3종만 제외돼야 한다."""

    def __init__(self, info):
        self._info = info

    def build_candidates(self, run_date, snapshot_at):
        return [_clean_cand("PREF"), _clean_cand("MGMT"),
                _clean_cand("WARN"), _clean_cand("CLEAN")]

    def fetch_live(self, tickers):
        return {t: LiveQuote(p_now=24500.0, cum_volume_1520=2500.0, day_change_pct=3.0,
                             is_limit_up=False, is_vi=False, is_halted=False)
                for t in tickers}

    def get_basic_info_bulk(self, tickers):
        return {t: self._info[t] for t in tickers if t in self._info}


def test_orchestrate_static_hygiene_excludes_preferred_managed_warning_from_board():
    """15:20 기본정보로 관리/경고/우선주 플래그를 채우면 실 run_pipeline 의 passes_static 이
    이들을 라이브 조회 전에 제외해 보드에 안 나온다. 정보 없는(=조회실패/미포함) 종목은
    제외되지 않는다(보수적 = 제외 안 함, fail-open 아님)."""
    info = {
        "PREF": _basic_info_o("PREF", preferred=True),
        "MGMT": _basic_info_o("MGMT", managed=True),
        "WARN": _basic_info_o("WARN", warning=True),
        # "CLEAN" 은 info 없음 → 원래 COMMON/False 유지(제외 안 됨)
    }
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=HygieneAdapter(info), store=DictStore())
    emitted = {r.ticker for r in res.recommendations}
    assert emitted == {"CLEAN"}                      # 부적격 3종 제외, 정보없는 CLEAN 만 발행


def test_orchestrate_static_hygiene_no_info_keeps_all_eligible():
    """get_basic_info_bulk 가 전부 빈(정보없음)이면 어떤 후보도 제외되지 않는다(보수적)."""
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=HygieneAdapter({}), store=DictStore())
    emitted = {r.ticker for r in res.recommendations}
    assert emitted == {"PREF", "MGMT", "WARN", "CLEAN"}   # 정보없음 → 전원 유지


class HygieneStore(DictStore):
    """update_universe_hygiene 호출을 기록하는 store 스파이."""

    def __init__(self):
        super().__init__()
        self.hygiene_updates = []

    def update_universe_hygiene(self, run_date, flags):
        self.hygiene_updates.append((run_date, dict(flags)))


def test_orchestrate_persists_hygiene_flags_to_universe_cache():
    """15:20 에 확인한 위생 플래그를 그 run_date 의 universe_cache 에 반영하도록
    store.update_universe_hygiene 를 호출해야 한다(prefetch 08:30 경로는 이 값을 모름)."""
    store = HygieneStore()
    info = {"PREF": _basic_info_o("PREF", preferred=True),
            "MGMT": _basic_info_o("MGMT", managed=True)}
    orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                    adapter=HygieneAdapter(info), store=store,
                    run_pipeline_fn=fake_run_pipeline)
    assert store.hygiene_updates                     # 위생조회 후 영속화 호출됨
    rd, flags = store.hygiene_updates[0]
    assert rd == date(2026, 6, 30)
    assert flags["PREF"]["is_preferred"] is True
    assert flags["MGMT"]["is_managed"] is True


def test_orchestrator_store_update_universe_hygiene_updates_existing_rows():
    """실 OrchestratorStore.update_universe_hygiene — run_date 행의 sec_type/is_managed/
    is_warning 를 갱신하고, 우선주는 sec_type='PREFERRED'. 행이 없으면 무시(방어적)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.store.models import Base, UniverseCache
    from app.store.orchestrator_store import OrchestratorStore

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    run_date = date(2026, 6, 30)
    with Session() as db:
        db.add(UniverseCache(ticker="005930", as_of=run_date, name="삼성전자우",
                             sec_type="COMMON", is_managed=False, is_warning=False))
        db.add(UniverseCache(ticker="000660", as_of=run_date, name="SK하이닉스",
                             sec_type="COMMON", is_managed=False, is_warning=False))
        db.commit()

    flags = {
        "005930": {"is_managed": False, "is_warning": False, "is_preferred": True},
        "000660": {"is_managed": True, "is_warning": True, "is_preferred": False},
        "999999": {"is_managed": True, "is_warning": False, "is_preferred": False},  # 행 없음
    }
    with Session() as db:
        OrchestratorStore(db).update_universe_hygiene(run_date, flags)
        db.commit()

    with Session() as db:
        pref = db.get(UniverseCache, ("005930", run_date))
        warn = db.get(UniverseCache, ("000660", run_date))
        missing = db.get(UniverseCache, ("999999", run_date))
    assert pref.sec_type == "PREFERRED"                  # 우선주 → 정적위생 제외군
    assert warn.is_managed is True and warn.is_warning is True
    assert warn.sec_type == "COMMON"                     # 우선주 아님 → sec_type 불변
    assert missing is None                               # 행 없으면 무시(에러 없음)


def test_orchestrate_uses_real_orchestrator_store_prefetch_end_to_end():
    """운영 seam: 실 OrchestratorStore.load_prefetch(final_cache)로 DB 영속화된 FINAL
    번들이 orchestrate_run 후보에 반영되어야 한다(load_prefetch 미소비 회귀 방지)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.store.models import Base, FinalPrefetch
    from app.store.orchestrator_store import OrchestratorStore

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    run_date = date(2026, 6, 30)
    with Session() as db:
        db.add(FinalPrefetch(run_date=run_date, ticker="005930", h_ref_252=111.0,
                             h_ref_60=99.0, atr20=4.5, avg_value_20d=7.0e8,
                             d1_supply_value=1.3e7))
        db.commit()

    captured = {}

    def capturing_pipeline(candidates, fetch_live, regime_by_market, modeled_avg,
                           veto_by_ticker, max_emit):
        captured["candidates"] = list(candidates)
        return fake_run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg,
                                 veto_by_ticker, max_emit)

    with Session() as db:
        orchestrate_run(run_date, datetime(2026, 6, 30, 15, 20), adapter=FakeAdapter(),
                        store=OrchestratorStore(db), run_pipeline_fn=capturing_pipeline)

    overlaid = {c.ticker: c for c in captured["candidates"]}["005930"]
    assert overlaid.high_252 == 111.0
    assert overlaid.avg_value_20d == 7.0e8
    assert overlaid.d1_supply_value == 1.3e7
