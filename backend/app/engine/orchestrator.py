"""오케스트레이터 (00 §3 정본 · B2·M4 해소).

플랜02의 **순수** ``run_pipeline(candidates, fetch_live, regime_by_market,
modeled_avg_by_ticker, veto_by_ticker, max_emit)`` 을 감싸 데이터 수집·시장별 레짐
산출/영속화·**15:20 거래량 스냅샷 upsert + trailing≥20 평균(MODELED RVOL 생산자)**·
veto 맵·``EngineRow→RecRow``·``coverage×100`` 을 수행한다.

adapter/store/run_pipeline_fn 은 모두 주입 경계 뒤에 있어 테스트는 네트워크 없이 동작한다.
``regime_by_market`` 은 00 §3 / 순수 엔진 계약대로 ``dict[str, float]``(시장별 regime_mult).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from app.engine.pipeline import run_pipeline as _run_pipeline
from app.engine.signals.regime import compute_regime


@dataclass
class RegimeInfo:
    market: str
    index_level: float
    ma5: float
    regime_mult: float
    cond_a: bool
    cond_b: bool


@dataclass
class RecRow:
    rank: int
    ticker: str
    name: str
    market: str
    price_provisional: float
    buy_price_provisional: float
    buy_price_final: float | None
    target_price: float
    stop_price: float
    s_shin: float
    s_geo: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    core: float
    final: float
    grade: str
    near_252: float
    near_60: float
    rvol: float
    spark: list
    base_flag: bool
    provisional_flag: bool = True


@dataclass
class RunResult:
    run_date: date
    session_type: str
    data_available: bool
    kis_coverage_pct: float            # 0~100
    recommendations: list
    regimes: dict
    reason: str | None = None


def compute_modeled_avg(trailing_values, min_sessions: int = 20):
    """trailing ≥min_sessions 이면 평균, 미만이면 None(=rvol_confirm 중립 1.0). (M4 RVOL 생산자)."""
    if len(trailing_values) < min_sessions:
        return None
    return sum(trailing_values) / len(trailing_values)


def orchestrate_run(run_date: date, snapshot_at: datetime, *, adapter, store,
                    run_pipeline_fn=_run_pipeline, d1_top_n: int = 200, live_top: int = 30,
                    rvol_min_sessions: int = 20, session_type: str = "정규", max_emit: int = 30) -> RunResult:
    # ① 후보풀 = D-1 거래대금 top-N ∪ 라이브 top-30×2 (스펙 §3.3 ①)
    pool = list(dict.fromkeys(
        adapter.d1_value_top(run_date, d1_top_n)
        + adapter.live_value_top("KOSPI", live_top) + adapter.live_value_top("KOSDAQ", live_top)))

    # ② 정적 위생 → ③ 라이브 시세 → ④ 동적 위생(과열·거래정지)
    quotes = {}
    for t in (x for x in pool if adapter.static_ok(x)):
        q = adapter.quote(t)
        if q is None:
            continue
        if q.is_halted or q.is_limit_up or q.is_vi or q.change_pct >= 20.0:
            continue
        quotes[t] = q
    candidates = list(quotes)
    coverage = (len(quotes) / len(pool)) if pool else 0.0

    # ⑤ 시장별 레짐 산출 + 영속화 (종목 소속시장 레짐)
    regimes: dict[str, RegimeInfo] = {}
    for market in ("KOSPI", "KOSDAQ"):
        idx, prev5 = adapter.regime_inputs(market)
        rr = compute_regime(idx, prev5)
        info = RegimeInfo(market=market, index_level=idx, ma5=rr.ma5, regime_mult=rr.regime_mult,
                          cond_a=rr.cond_a, cond_b=rr.cond_b)
        regimes[market] = info
        store.save_regime(run_date, market, info)
    regime_by_market = {m: r.regime_mult for m, r in regimes.items()}   # dict[str, float]

    # ⑥ MODELED RVOL 생산자: 당일 15:20 스냅샷 upsert + trailing≥20 평균
    modeled_avg = {}
    for t, q in quotes.items():
        store.upsert_volume_snapshot(t, run_date, q.cum_volume, q.cum_value)
        modeled_avg[t] = compute_modeled_avg(store.trailing_volume(t, run_date), rvol_min_sessions)

    # ⑦ veto 맵
    veto_by_ticker = {t: adapter.veto(t, snapshot_at) for t in candidates}

    # ⑧ 순수 엔진 호출 → EngineRow→RecRow, coverage×100
    def fetch_live(t):
        return quotes[t]

    pr = run_pipeline_fn(candidates, fetch_live, regime_by_market, modeled_avg, veto_by_ticker, max_emit)
    recs = [RecRow(rank=i + 1, ticker=e.ticker, name=e.name, market=e.market,
                   price_provisional=e.price, buy_price_provisional=e.buy, buy_price_final=None,
                   target_price=e.target, stop_price=e.stop, s_shin=e.s_shin, s_geo=e.s_geo,
                   rvol_confirm=e.rvol_confirm, supply_tilt=e.supply_tilt, regime_mult=e.regime_mult,
                   veto=e.veto, core=e.core, final=e.final, grade=e.grade, near_252=e.near_252,
                   near_60=e.near_60, rvol=e.rvol, spark=e.spark, base_flag=e.base_flag)
            for i, e in enumerate(pr.rows)]
    return RunResult(run_date=run_date, session_type=session_type,
                     data_available=bool(quotes), kis_coverage_pct=round(coverage * 100, 1),
                     recommendations=recs, regimes=regimes, reason=pr.reason)
