"""오케스트레이터 (00 §3 정본 · B2·M4 해소).

플랜02의 **순수** ``run_pipeline(candidates, fetch_live, regime_by_market,
modeled_avg_by_ticker, veto_by_ticker, max_emit)`` 을 감싸 데이터 수집·시장별 레짐
산출/영속화·**15:20 거래량 스냅샷 upsert + trailing≥20 평균(MODELED RVOL 생산자)**·
veto 맵·``EngineRow→RecRow``·``coverage×100`` 을 수행한다.

adapter/store/run_pipeline_fn 은 모두 주입 경계 뒤에 있어 테스트는 네트워크 없이 동작한다.
``regime_by_market`` 은 00 §3 / 순수 엔진 계약대로 ``dict[str, float]``(시장별 regime_mult).
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime

from app.engine.pipeline import run_pipeline as _run_pipeline
from app.engine.signals.regime import compute_regime


@dataclass
class RegimeInfo:
    market: str
    index_level: float
    ma5: float
    ma5_prev: float          # 전일 5MA — cond_b(5MA 기울기) 감사용, 영속화 대상
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


def _apply_prefetch(candidate, row):
    """장전 FINAL 캐시 행(FinalPrefetch)의 FINAL 지표를 StaticCandidate 에 오버레이.

    prefetch 값이 None 이면 후보의 기존값을 유지한다(장전 계산이 성립한 필드만 대체)."""
    return replace(
        candidate,
        high_252=row.h_ref_252 if row.h_ref_252 is not None else candidate.high_252,
        high_60=row.h_ref_60 if row.h_ref_60 is not None else candidate.high_60,
        atr20=row.atr20 if row.atr20 is not None else candidate.atr20,
        avg_value_20d=(row.avg_value_20d if row.avg_value_20d is not None
                       else candidate.avg_value_20d),
        d1_supply_value=(row.d1_supply_value if row.d1_supply_value is not None
                         else candidate.d1_supply_value),
    )


def orchestrate_run(run_date: date, snapshot_at: datetime, *, adapter, store,
                    run_pipeline_fn=_run_pipeline, rvol_min_sessions: int = 20,
                    session_type: str = "정규", max_emit: int = 30) -> RunResult:
    # ① 후보풀 = 실 StaticCandidate 리스트 (어댑터가 prefetch/랭킹으로 구성)
    candidates = list(adapter.build_candidates(run_date, snapshot_at))
    # ①' 장전 영속화된 FINAL 번들(H_ref/ATR20/avg_value_20d/D-1 순매수)을 로드해 후보에 오버레이
    load_prefetch = getattr(store, "load_prefetch", None)
    if load_prefetch is not None:
        prefetch = load_prefetch(run_date)
        if prefetch:
            candidates = [
                _apply_prefetch(c, prefetch[c.ticker]) if c.ticker in prefetch else c
                for c in candidates
            ]
    tickers = [c.ticker for c in candidates]

    # ② 라이브 시세 (벌크, 부분 실패 허용) → Mapping[str, LiveQuote]
    quotes = dict(adapter.fetch_live(tickers))

    # ③ MODELED RVOL 생산자: 당일 15:20 스냅샷 upsert + trailing≥20 평균 (cum_value 없음)
    modeled_avg = {}
    for t, q in quotes.items():
        store.upsert_volume_snapshot(t, run_date, q.cum_volume_1520, None)
        modeled_avg[t] = compute_modeled_avg(store.trailing_volume(t, run_date), rvol_min_sessions)

    # ④ 시장별 레짐 산출 + 영속화 (종목 소속시장 레짐)
    regimes: dict[str, RegimeInfo] = {}
    for market in ("KOSPI", "KOSDAQ"):
        idx, prev5 = adapter.regime_inputs(market)
        rr = compute_regime(idx, prev5)
        info = RegimeInfo(market=market, index_level=idx, ma5=rr.ma5, ma5_prev=rr.ma5_prev,
                          regime_mult=rr.regime_mult, cond_a=rr.cond_a, cond_b=rr.cond_b)
        regimes[market] = info
        store.save_regime(run_date, market, info)
    regime_by_market = {m: r.regime_mult for m, r in regimes.items()}   # dict[str, float]

    # ⑤ veto 맵 (snapshot_at 을 그대로 전달)
    veto_by_ticker = {t: adapter.dilution_veto(t, snapshot_at) for t in tickers}

    # ⑥ 순수 엔진 호출 (fetch_live: List[str] -> Mapping[str, LiveQuote]) → EngineRow→RecRow
    def fetch_live(requested):
        return {t: quotes[t] for t in requested if t in quotes}

    pr = run_pipeline_fn(candidates, fetch_live, regime_by_market, modeled_avg, veto_by_ticker, max_emit)
    recs = [RecRow(rank=e.rank, ticker=e.ticker, name=e.name, market=e.market,
                   price_provisional=e.price_provisional,
                   buy_price_provisional=e.buy_price_provisional, buy_price_final=None,
                   target_price=e.target_price, stop_price=e.stop_price, s_shin=e.s_shin,
                   s_geo=e.s_geo, rvol_confirm=e.rvol_confirm, supply_tilt=e.supply_tilt,
                   regime_mult=e.regime_mult, veto=e.veto, core=e.core, final=e.final,
                   grade=e.grade, near_252=e.near_252, near_60=e.near_60, rvol=e.rvol,
                   spark=e.spark, base_flag=e.base_flag)
            for e in pr.rows]
    # ⑦ 커버리지는 파이프라인 자체 coverage_pct × 100 (계약 §3.6)
    return RunResult(run_date=run_date, session_type=session_type,
                     data_available=bool(quotes),
                     kis_coverage_pct=round(pr.coverage_pct * 100, 1),
                     recommendations=recs, regimes=regimes, reason=pr.reason)
