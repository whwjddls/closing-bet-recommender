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
