from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import HealthResponse
from app.store.db import get_db
from app.store.models import Run

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    last_run = db.scalars(
        select(Run).order_by(Run.run_date.desc()).limit(1)).first()
    if last_run is None:
        return HealthResponse(status="DOWN", reason="런 기록 없음",
                              kis_coverage_pct=0.0, board_published=False, last_run_date=None)
    if last_run.status == "OK" and last_run.board_published:
        status, reason = "OK", "정상"
    else:
        status, reason = "DEGRADED", (last_run.reason or last_run.status or "미발행")
    return HealthResponse(
        status=status,
        reason=reason,
        kis_coverage_pct=last_run.kis_coverage_pct or 0.0,
        board_published=bool(last_run.board_published),
        last_run_date=last_run.run_date.isoformat(),
    )
