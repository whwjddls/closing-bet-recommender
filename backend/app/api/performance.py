import math
from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import (
    CurvePoint,
    GradeBucket,
    PerformanceAggregate,
    PerformanceResponse,
    PickResult,
    RegimeBucket,
)
from app.store.db import get_db
from app.store.models import Performance, Recommendation

router = APIRouter(tags=["performance"])
COLD_START_MIN = 30
WILSON_Z_95 = 1.96                      # 95% 신뢰구간 z값
GAP_DOWN_THRESHOLD = 0.02              # morning_return < -0.02 → 갭하락, else 장중반전


def wilson_ci(successes: int, n: int, z: float = WILSON_Z_95) -> tuple[float, float]:
    """이항 성공률(hit_rate) Wilson 점수 신뢰구간. [0,1]로 클램프. n=0이면 (0,0)."""
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1.0 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def compute_mdd(cum_values: list[float]) -> float:
    """누적곡선 최대낙폭(peak-to-trough, 양수 크기). 빈 곡선이면 0."""
    if not cum_values:
        return 0.0
    peak = cum_values[0]
    mdd = 0.0
    for cum in cum_values:
        peak = max(peak, cum)
        mdd = max(mdd, peak - cum)
    return mdd


def compute_payoff_ratio(returns: list[float]) -> float:
    """손익비 = 평균이익 / |평균손실|. 이익 또는 손실 표본이 없으면 0."""
    profits = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    if not profits or not losses:
        return 0.0
    avg_profit = sum(profits) / len(profits)
    avg_loss = abs(sum(losses) / len(losses))
    return avg_profit / avg_loss if avg_loss else 0.0


def compute_max_consec_loss_days(daily_returns: dict) -> int:
    """최대 연속 손실일 — 일별 합(morning_return) < 0 이 연속된 최대 길이."""
    streak = best = 0
    for d in sorted(daily_returns):
        if daily_returns[d] < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def classify_fail_reason(outcome: str, morning_return: float | None) -> str | None:
    """FAIL 픽 원인 분류. 비-FAIL은 None. morning_return < -임계면 갭하락, 아니면 장중반전."""
    if outcome != "FAIL":
        return None
    if morning_return is not None and morning_return < -GAP_DOWN_THRESHOLD:
        return "갭하락"
    return "장중반전"


def get_benchmark_provider() -> Callable:
    """KOSPI 벤치마크 누적수익 곡선 공급자. 테스트는 dependency_overrides 로 주입.
    실 구현은 호출 시점 지연 임포트 — pykrx 네트워크는 provider 호출 때만 발생."""
    def _provider(start: date, end: date) -> list[dict]:
        from app.data.pykrx_client import kospi_index_curve
        return kospi_index_curve(start, end)
    return _provider


@router.get("/performance", response_model=PerformanceResponse)
def get_performance(db: Session = Depends(get_db),
                    benchmark: Callable = Depends(get_benchmark_provider)) -> PerformanceResponse:
    pairs = db.execute(
        select(Performance, Recommendation)
        .join(Recommendation, Performance.rec_id == Recommendation.id)
        .order_by(Performance.eval_date.desc(), Recommendation.rank)
    ).all()

    picks: list[PickResult] = []
    success = fail = 0
    ret_sum = 0.0
    scored_returns: list[float] = []         # 채점 픽 morning_return (손익비용)
    by_grade: dict[str, list[int]] = {}      # grade -> [success, fail]
    by_regime: dict[str, list[int]] = {}     # regime_mult(str) -> [success, fail]
    curve_by_date: dict = {}                 # eval_date -> sum(morning_return) (채점분)
    latest_eval = None

    for perf, rec in pairs:
        picks.append(PickResult(
            ticker=rec.ticker, name=rec.name or "", grade=rec.grade or "",
            buy_price_final=perf.buy_price_final, vwap_0900_0920=perf.vwap_0900_0920,
            morning_return=perf.morning_return, outcome=perf.outcome,
            dart_overnight_flag=perf.dart_overnight_flag,
            fail_reason=classify_fail_reason(perf.outcome, perf.morning_return),
        ))
        if latest_eval is None or perf.eval_date > latest_eval:
            latest_eval = perf.eval_date
        if perf.outcome == "NA":                          # NA → 분모 제외
            continue
        is_ok = perf.outcome == "SUCCESS"
        success += int(is_ok)
        fail += int(not is_ok)
        if perf.morning_return is not None:
            ret_sum += perf.morning_return
            scored_returns.append(perf.morning_return)
            curve_by_date[perf.eval_date] = curve_by_date.get(perf.eval_date, 0.0) + perf.morning_return
        by_grade.setdefault(rec.grade, [0, 0])[0 if is_ok else 1] += 1
        by_regime.setdefault(f"{rec.regime_mult}", [0, 0])[0 if is_ok else 1] += 1

    sample_size = success + fail
    cum = 0.0
    curve: list[CurvePoint] = []
    for d in sorted(curve_by_date):
        cum += curve_by_date[d]
        curve.append(CurvePoint(date=d.isoformat(), cum=round(cum, 6)))

    benchmark_curve: list[CurvePoint] = []
    if curve_by_date:
        try:
            bench_rows = benchmark(min(curve_by_date), max(curve_by_date))
        except Exception:                                 # noqa: BLE001  (벤치마크 graceful)
            bench_rows = []
        benchmark_curve = [CurvePoint(date=r["date"], cum=round(r["cum"], 6)) for r in bench_rows]

    aggregate = PerformanceAggregate(
        sample_size=sample_size,
        hit_rate=(success / sample_size) if sample_size else 0.0,
        avg_morning_return=(ret_sum / sample_size) if sample_size else 0.0,
        cumulative_curve=curve,
        by_grade=[_grade_bucket(g, s, f) for g, (s, f) in by_grade.items()],
        by_regime=[_regime_bucket(r, s, f) for r, (s, f) in by_regime.items()],
        cold_start=sample_size < COLD_START_MIN,
        mdd=round(compute_mdd([p.cum for p in curve]), 6),
        payoff_ratio=round(compute_payoff_ratio(scored_returns), 6),
        max_consec_losses=compute_max_consec_loss_days(curve_by_date),
        benchmark_curve=benchmark_curve,
    )
    return PerformanceResponse(
        eval_date=latest_eval.isoformat() if latest_eval else "",
        picks=picks, aggregate=aggregate,
    )


def _grade_bucket(grade: str, success: int, fail: int) -> GradeBucket:
    n = success + fail
    low, high = wilson_ci(success, n)
    return GradeBucket(grade=grade, hit_rate=success / n, n=n, ci_low=low, ci_high=high)


def _regime_bucket(regime: str, success: int, fail: int) -> RegimeBucket:
    n = success + fail
    low, high = wilson_ci(success, n)
    return RegimeBucket(regime=regime, hit_rate=success / n, n=n, ci_low=low, ci_high=high)
