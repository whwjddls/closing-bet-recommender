"""오케스트레이터 (00 §3 정본 · B2·M4 해소).

플랜02의 **순수** ``run_pipeline(candidates, fetch_live, regime_by_market,
modeled_avg_by_ticker, veto_by_ticker, max_emit)`` 을 감싸 데이터 수집·시장별 레짐
산출/영속화·**15:20 거래량 스냅샷 upsert + trailing≥20 평균(MODELED RVOL 생산자)**·
veto 맵·``EngineRow→RecRow``·``coverage×100`` 을 수행한다.

adapter/store/run_pipeline_fn 은 모두 주입 경계 뒤에 있어 테스트는 네트워크 없이 동작한다.
``regime_by_market`` 은 00 §3 / 순수 엔진 계약대로 ``dict[str, float]``(시장별 regime_mult).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import date, datetime

from app.engine.pipeline import run_pipeline as _run_pipeline
from app.engine.signals.regime import compute_regime

logger = logging.getLogger(__name__)


def _try(fn, default):
    """옵션 콜라보레이터 호출 — 미구현/조회 실패는 default 로 흡수(graceful)."""
    if fn is None:
        return default
    try:
        return fn()
    except Exception:                                   # noqa: BLE001  (외부 IO/미구현 방어)
        return default


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
    exp_close: float | None = None       # KIS 예상 체결가(잠정 — 확정 종가 아님)
    supply_today: str | None = None      # 당일 외인/기관 가집계 라벨(잠정 — D-1 확정 아님)


@dataclass
class RunResult:
    run_date: date
    session_type: str
    data_available: bool
    kis_coverage_pct: float            # 0~100
    recommendations: list
    regimes: dict
    reason: str | None = None
    funnel: dict | None = None         # 단계별 생존 수 — 빈 보드 원인 진단용(계측)


def compute_modeled_avg(trailing_values, min_sessions: int = 20):
    """trailing ≥min_sessions 이면 평균, 미만이면 None(=rvol_confirm 중립 1.0). (M4 RVOL 생산자)."""
    if len(trailing_values) < min_sessions:
        return None
    return sum(trailing_values) / len(trailing_values)


def _build_candidates(adapter, run_date, snapshot_at, prefetch):
    """어댑터가 prefetch 파라미터를 지원하면 캐시 유니버스를 넘겨 풀을 확장한다.

    구형 어댑터(테스트 페이크 등)는 prefetch 시그니처가 없으므로 하위호환 호출한다."""
    import inspect

    try:
        supports = "prefetch" in inspect.signature(adapter.build_candidates).parameters
    except (TypeError, ValueError):
        supports = False
    if supports:
        return adapter.build_candidates(run_date, snapshot_at, prefetch=prefetch)
    return adapter.build_candidates(run_date, snapshot_at)


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
    # ①' 장전 영속화된 FINAL 캐시(H_ref/ATR20/avg_value_20d/D-1 순매수)를 먼저 로드
    prefetch = {}
    load_prefetch = getattr(store, "load_prefetch", None)
    if load_prefetch is not None:
        prefetch = load_prefetch(run_date) or {}
    # ① 후보풀 = 실 StaticCandidate 리스트 (캐시 유니버스 ∪ 라이브 톱30×2)
    candidates = list(_build_candidates(adapter, run_date, snapshot_at, prefetch))
    # ①'' 캐시값을 후보에 오버레이(라이브 폴백으로 구성된 종목의 FINAL 지표 대체·정합)
    if prefetch:
        candidates = [
            _apply_prefetch(c, prefetch[c.ticker]) if c.ticker in prefetch else c
            for c in candidates
        ]
    tickers = [c.ticker for c in candidates]

    # ② 라이브 시세 (벌크, 부분 실패 허용) → Mapping[str, LiveQuote]
    quotes = dict(adapter.fetch_live(tickers))

    # ②' 과열가드 정확화: 실제 VI∪상한가 리스트를 1회씩 조회해 후보 플래그 보강.
    #     기존 등락률 폴백(LiveQuote.is_vi/is_limit_up)과 OR 결합. 조회 실패 시 폴백만.
    vi_set = _try(getattr(adapter, "get_vi_tickers", None), set())
    limit_set = _try(getattr(adapter, "get_limit_up_tickers", None), set())
    if vi_set or limit_set:
        for t, q in list(quotes.items()):
            new_vi = q.is_vi or (t in vi_set)
            new_limit = q.is_limit_up or (t in limit_set)
            if new_vi != q.is_vi or new_limit != q.is_limit_up:
                quotes[t] = replace(q, is_vi=new_vi, is_limit_up=new_limit)

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

    # ⑥' 신호 배선: 예상 체결가·당일 외인/기관 가집계(둘 다 잠정 라벨) 1회씩 조회
    exp_map = _try(getattr(adapter, "get_exp_closing_prices", None), {})
    flow_map = _try(getattr(adapter, "get_provisional_flows", None), {})
    recs = [RecRow(rank=e.rank, ticker=e.ticker, name=e.name, market=e.market,
                   price_provisional=e.price_provisional,
                   buy_price_provisional=e.buy_price_provisional, buy_price_final=None,
                   target_price=e.target_price, stop_price=e.stop_price, s_shin=e.s_shin,
                   s_geo=e.s_geo, rvol_confirm=e.rvol_confirm, supply_tilt=e.supply_tilt,
                   regime_mult=e.regime_mult, veto=e.veto, core=e.core, final=e.final,
                   grade=e.grade, near_252=e.near_252, near_60=e.near_60, rvol=e.rvol,
                   spark=e.spark, base_flag=e.base_flag,
                   exp_close=exp_map.get(e.ticker), supply_today=flow_map.get(e.ticker))
            for e in pr.rows]

    # ⑥'' 최종 위생: emit된 top-N만 종목정보 조회로 관리/경고/우선주 부적격 제외.
    #      조회 실패는 '통과(스킵하되 로그)' — fail-open 아님(보조 필터).
    before_hygiene = len(recs)
    recs = _apply_final_hygiene(adapter, recs)

    # ⑦ 커버리지는 파이프라인 자체 coverage_pct × 100 (계약 §3.6)
    pr_funnel = getattr(pr, "funnel", None)  # 주입 seam(구형 fake)은 퍼널이 없을 수 있다
    funnel = pr_funnel.to_dict() if pr_funnel is not None else {}
    funnel["final_hygiene_dropped"] = before_hygiene - len(recs)
    funnel["published"] = len(recs)          # 최종 위생 반영 실 발행 수
    logger.info("funnel %s reason=%s", funnel, pr.reason)
    return RunResult(run_date=run_date, session_type=session_type,
                     data_available=bool(quotes),
                     kis_coverage_pct=round(pr.coverage_pct * 100, 1),
                     recommendations=recs, regimes=regimes, reason=pr.reason,
                     funnel=funnel)


def _apply_final_hygiene(adapter, recs):
    """emit된 추천만 search-stock-info 로 부적격(관리/경고/우선주) 제외 후 재랭킹."""
    get_info = getattr(adapter, "get_stock_basic_info", None)
    if get_info is None or not recs:
        return recs
    kept = []
    for r in recs:
        info = _try(lambda: get_info(r.ticker), None)
        if not info:                                    # 조회 실패/빈 결과 → 스킵하되 통과
            logger.info("final hygiene: %s 종목정보 조회 실패 → 통과", r.ticker)
            kept.append(r)
            continue
        if info.get("is_ineligible"):
            logger.info("final hygiene: %s 부적격 제외(%s)", r.ticker, info)
            continue
        kept.append(r)
    for i, r in enumerate(kept):                        # 제외로 생긴 랭크 공백 메움
        r.rank = i + 1
    return kept
