"""15:20 추천 파이프라인 오케스트레이션 ①~⑥.

①후보풀(주입) → ②정적위생(라이브 전, 레이트버짓 보호) → ③라이브조회(주입 fetch_live)
→ ④동적위생(과열·정지) → 게이트(regime/veto) → 신호 → core/final
→ emit(final>0) 내림차순 top30, tie-break=D-1 거래대금. 빈보드/저레짐/저커버리지 처리.

서브시스템 1 의존: fetch_live(KIS 라이브 시세), regime_by_market(시황 사전계산),
modeled_avg_by_ticker(RVOL 분모 축적), veto_by_ticker(DART veto 사전계산).
veto/modeled 미지정은 fail-closed/중립 규칙을 따른다.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, List, Mapping, Optional, Sequence, Tuple

from app.engine.signals import hygiene
from app.engine.signals.breakout import s_shin
from app.engine.signals.rvol import compute_rvol, rvol_confirm, s_geo
from app.engine.signals.supply import supply_tilt, supply_z
from app.engine.scoring import core_score, final_score
from app.engine.grade import grade_of
from app.engine.pricing import freeze_prices

MIN_COVERAGE = 0.70
MAX_EMIT = 30
VETO_FAIL_CLOSED = 0
# base_flag(베이스 배지) 조-baseline 휴리스틱: 60일 고가 근접(=베이스 상단)이면 True.
BASE_NEAR_60_FLOOR = 0.97


@dataclass(frozen=True)
class StaticCandidate:
    ticker: str
    name: str
    market: str                 # "KOSPI" | "KOSDAQ"
    sec_type: str
    avg_value_20d: float
    is_managed: bool
    is_warning: bool
    is_caution: bool
    listing_days: int
    high_60: float
    high_252: Optional[float]
    prev_high: float
    atr20: float
    d1_supply_value: float
    d1_value: float             # tie-break
    recent_closes: Tuple[float, ...] = ()   # 스파크라인용 최근 확정 종가(정규화 전)


@dataclass(frozen=True)
class LiveQuote:
    p_now: float
    cum_volume_1520: float
    day_change_pct: float
    is_limit_up: bool
    is_vi: bool
    is_halted: bool


@dataclass(frozen=True)
class EngineRow:
    rank: int
    ticker: str
    name: str
    market: str
    price_provisional: float
    buy_price_provisional: float
    s_shin: float
    s_geo: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    core: float
    final: float
    grade: Optional[str]
    near_252: Optional[float]
    near_60: float
    rvol: Optional[float]
    target_price: float
    stop_price: float
    d1_value: float
    spark: List[float] = field(default_factory=list)   # 정규화된 최근 종가 series
    base_flag: bool = False                            # 베이스(조) 돌파 배지
    provisional_flag: bool = True


@dataclass(frozen=True)
class Funnel:
    """단계별 생존 수 — 빈 보드의 원인을 사후 재구성 없이 바로 읽기 위한 계측.

    보드가 비었을 때 '전략이 보수적이라서'인지 '버그로 특정 게이트가 전멸시켜서'인지
    구분하려면 이 카운트가 필요하다(veto 전멸·우선주 오판 버그를 수동 재구성으로
    찾느라 몇 시간 걸린 재발 방지)."""
    candidates: int = 0         # ① 후보풀
    static_ok: int = 0          # ② 정적위생 통과
    quotes: int = 0             # ③ 라이브 시세 수신
    dynamic_ok: int = 0         # ④ 동적위생(과열·정지) 통과
    shin_zero: int = 0          #    └ 이 중 s_신=0 (돌파 근접 미달)
    veto_blocked: int = 0       #    └ 이 중 veto=0 (희석공시·미매핑 fail-closed)
    regime_zero: int = 0        #    └ 이 중 regime=0 (리스크오프 시장)
    emitted: int = 0            # ⑤ final>0 (랭킹 캡 적용 전)
    published: int = 0          # ⑥ top-N 컷 후 발행

    def to_dict(self) -> dict:
        return {
            "candidates": self.candidates, "static_ok": self.static_ok,
            "quotes": self.quotes, "dynamic_ok": self.dynamic_ok,
            "shin_zero": self.shin_zero, "veto_blocked": self.veto_blocked,
            "regime_zero": self.regime_zero, "emitted": self.emitted,
            "published": self.published,
        }


@dataclass(frozen=True)
class PipelineResult:
    published: bool
    reason: str                 # OK | RISK_OFF | EMPTY_UNIVERSE | LOW_COVERAGE | NO_DATA
    rows: List[EngineRow]
    coverage_pct: float
    funnel: Funnel = field(default_factory=Funnel)


def _normalized_spark(recent_closes: Sequence[float]) -> List[float]:
    """최근 확정 종가를 피크(최댓값) 대비 0~1 로 정규화한 스파크라인 series."""
    closes = [float(c) for c in recent_closes]
    if not closes:
        return []
    peak = max(closes)
    if peak <= 0:
        return []
    return [round(c / peak, 4) for c in closes]


def run_pipeline(
    candidates: Sequence[StaticCandidate],
    fetch_live: Callable[[List[str]], Mapping[str, LiveQuote]],
    regime_by_market: Mapping[str, float],
    modeled_avg_by_ticker: Mapping[str, Optional[float]],
    veto_by_ticker: Mapping[str, int],
    max_emit: int = MAX_EMIT,
) -> PipelineResult:
    # ② 정적 위생 (라이브 조회 전 — 레이트버짓 보호)
    static_ok = [
        c for c in candidates
        if hygiene.passes_static(
            c.sec_type, c.avg_value_20d, c.is_managed, c.is_warning,
            c.is_caution, c.listing_days,
        )
    ]
    base = dict(candidates=len(candidates), static_ok=len(static_ok))
    if not static_ok:
        return PipelineResult(True, "EMPTY_UNIVERSE", [], 0.0, Funnel(**base))

    # ③ 라이브 조회 (통과분만)
    requested = [c.ticker for c in static_ok]
    quotes = fetch_live(requested)
    if not quotes:
        return PipelineResult(False, "NO_DATA", [], 0.0, Funnel(**base))
    coverage = len(quotes) / len(requested)
    base["quotes"] = len(quotes)
    if coverage < MIN_COVERAGE:
        return PipelineResult(False, "LOW_COVERAGE", [], coverage, Funnel(**base))

    rows: List[EngineRow] = []
    dynamic_ok = shin_zero = veto_blocked = regime_zero = 0
    for c in static_ok:
        q = quotes.get(c.ticker)
        if q is None:
            continue
        # ④ 동적 위생 (과열·거래정지)
        if not hygiene.passes_dynamic(q.day_change_pct, q.is_limit_up, q.is_vi, q.is_halted):
            continue
        dynamic_ok += 1
        # 신호
        b = s_shin(q.p_now, c.high_60, c.high_252, c.listing_days)
        rvol = compute_rvol(q.cum_volume_1520, modeled_avg_by_ticker.get(c.ticker))
        confirm = rvol_confirm(rvol)
        sgeo = s_geo(rvol) if rvol is not None else 0.0
        tilt = supply_tilt(supply_z(c.d1_supply_value, c.avg_value_20d))
        regime_mult = regime_by_market.get(c.market, 0.0)
        veto = veto_by_ticker.get(c.ticker, VETO_FAIL_CLOSED)
        core = core_score(b.s_shin, confirm, tilt)
        final = final_score(core, regime_mult, veto)
        # 탈락 사유 계측(중복 집계 — 한 종목이 여러 축에서 동시에 0일 수 있다)
        if b.s_shin <= 0:
            shin_zero += 1
        if veto == 0:
            veto_blocked += 1
        if regime_mult == 0:
            regime_zero += 1
        if final <= 0:
            continue   # emit 규칙: final > 0
        pricing = freeze_prices(q.p_now, c.atr20, c.prev_high)
        base_flag = b.near_60 >= BASE_NEAR_60_FLOOR          # 조-baseline 휴리스틱
        rows.append(EngineRow(
            rank=0, ticker=c.ticker, name=c.name, market=c.market,
            price_provisional=q.p_now,
            buy_price_provisional=pricing.buy_price_provisional,
            s_shin=b.s_shin, s_geo=sgeo, rvol_confirm=confirm, supply_tilt=tilt,
            regime_mult=regime_mult, veto=veto, core=core, final=final,
            grade=grade_of(core), near_252=b.near_252, near_60=b.near_60, rvol=rvol,
            target_price=pricing.target_price, stop_price=pricing.stop_price,
            d1_value=c.d1_value,
            spark=_normalized_spark(c.recent_closes), base_flag=base_flag,
        ))

    stages = dict(base, dynamic_ok=dynamic_ok, shin_zero=shin_zero,
                  veto_blocked=veto_blocked, regime_zero=regime_zero, emitted=len(rows))
    if not rows:
        return PipelineResult(True, "RISK_OFF", [], coverage, Funnel(**stages))

    # ⑥ 랭킹: final 내림차순, tie-break = D-1 거래대금 내림차순
    rows.sort(key=lambda r: (-r.final, -r.d1_value))
    ranked = [replace(r, rank=i + 1) for i, r in enumerate(rows[:max_emit])]
    return PipelineResult(True, "OK", ranked, coverage,
                          Funnel(**stages, published=len(ranked)))
