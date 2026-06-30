from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import UniverseResponse, UniverseRow
from app.store.db import get_db
from app.store.models import UniverseCache

router = APIRouter(tags=["universe"])


@router.get("/universe", response_model=UniverseResponse)
def get_universe(db: Session = Depends(get_db)) -> UniverseResponse:
    latest = db.scalars(select(UniverseCache.as_of).order_by(UniverseCache.as_of.desc()).limit(1)).first()
    if latest is None:
        return UniverseResponse()
    rows = db.scalars(
        select(UniverseCache).where(UniverseCache.as_of == latest).order_by(UniverseCache.ticker)
    ).all()
    models = [UniverseRow.model_validate(r) for r in rows]
    return UniverseResponse(
        as_of=latest, total=len(models),
        eligible_count=sum(1 for r in models if r.eligible), rows=models,
    )
