from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ReminderPick, ReminderResponse
from app.store.db import get_db
from app.store.models import Performance, Recommendation

router = APIRouter(tags=["reminder"])


@router.get("/reminder", response_model=ReminderResponse)
def get_reminder(db: Session = Depends(get_db)) -> ReminderResponse:
    """익일 오전 청산 리마인더 — 추천이 존재하는 가장 최근 run_date 의 픽을 반환.
    target/stop 은 Recommendation, buy_price 는 final ?? provisional,
    outcome/morning_vwap 는 Performance 가 있을 때만 채움(미채점 시 None)."""
    latest_run = db.execute(select(func.max(Recommendation.run_date))).scalar()
    if latest_run is None:                       # 추천 없음 → graceful empty
        return ReminderResponse(picks=[])

    pairs = db.execute(
        select(Recommendation, Performance)
        .outerjoin(Performance, Performance.rec_id == Recommendation.id)
        .where(Recommendation.run_date == latest_run)
        .order_by(Recommendation.rank)
    ).all()

    picks = [
        ReminderPick(
            ticker=rec.ticker,
            name=rec.name or "",
            grade=rec.grade or "",
            buy_price=rec.buy_price_final if rec.buy_price_final is not None
            else rec.buy_price_provisional,
            target_price=rec.target_price,
            stop_price=rec.stop_price,
            outcome=perf.outcome if perf is not None else None,
            morning_vwap=perf.vwap_0900_1000 if perf is not None else None,
        )
        for rec, perf in pairs
    ]
    return ReminderResponse(picks=picks)
