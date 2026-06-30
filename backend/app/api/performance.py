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


@router.get("/performance", response_model=PerformanceResponse)
def get_performance(db: Session = Depends(get_db)) -> PerformanceResponse:
    pairs = db.execute(
        select(Performance, Recommendation)
        .join(Recommendation, Performance.rec_id == Recommendation.id)
        .order_by(Performance.eval_date.desc(), Recommendation.rank)
    ).all()

    picks: list[PickResult] = []
    success = fail = 0
    ret_sum = 0.0
    by_grade: dict[str, list[int]] = {}      # grade -> [success, fail]
    by_regime: dict[str, list[int]] = {}     # regime_mult(str) -> [success, fail]
    curve_by_date: dict = {}                 # eval_date -> sum(morning_return) (채점분)
    latest_eval = None

    for perf, rec in pairs:
        picks.append(PickResult(
            ticker=rec.ticker, name=rec.name, grade=rec.grade,
            buy_price_final=perf.buy_price_final, vwap_0900_1000=perf.vwap_0900_1000,
            morning_return=perf.morning_return, outcome=perf.outcome,
            dart_overnight_flag=perf.dart_overnight_flag,
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
            curve_by_date[perf.eval_date] = curve_by_date.get(perf.eval_date, 0.0) + perf.morning_return
        by_grade.setdefault(rec.grade, [0, 0])[0 if is_ok else 1] += 1
        by_regime.setdefault(f"{rec.regime_mult}", [0, 0])[0 if is_ok else 1] += 1

    sample_size = success + fail
    cum = 0.0
    curve: list[CurvePoint] = []
    for d in sorted(curve_by_date):
        cum += curve_by_date[d]
        curve.append(CurvePoint(date=d.isoformat(), cum=round(cum, 6)))

    aggregate = PerformanceAggregate(
        sample_size=sample_size,
        hit_rate=(success / sample_size) if sample_size else 0.0,
        avg_morning_return=(ret_sum / sample_size) if sample_size else 0.0,
        cumulative_curve=curve,
        by_grade=[GradeBucket(grade=g, hit_rate=s / (s + f), n=s + f) for g, (s, f) in by_grade.items()],
        by_regime=[RegimeBucket(regime=r, hit_rate=s / (s + f), n=s + f) for r, (s, f) in by_regime.items()],
        cold_start=sample_size < COLD_START_MIN,
    )
    return PerformanceResponse(
        eval_date=latest_eval.isoformat() if latest_eval else "",
        picks=picks, aggregate=aggregate,
    )
