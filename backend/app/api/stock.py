from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import BaseBox, Candle, StockDetailResponse
from app.store.db import get_db
from app.store.models import Recommendation

router = APIRouter(tags=["stock"])


def get_chart_provider() -> Callable:
    """차트 데이터 공급자(캔들·52주최고·직전고점·베이스박스). 테스트는 dependency_overrides 로 주입.
    실제 구현은 호출 시점 지연 임포트라 404(rec 없음) 경로에선 임포트가 일어나지 않는다."""
    def _provider(code: str, run_date: date) -> dict:
        from app.data.pykrx_client import get_stock_chart
        return get_stock_chart(code, run_date)
    return _provider


@router.get("/stock/{code}", response_model=StockDetailResponse)
def get_stock(code: str, on: date | None = None, db: Session = Depends(get_db),
              chart: Callable = Depends(get_chart_provider)) -> StockDetailResponse:
    stmt = select(Recommendation).where(Recommendation.ticker == code)
    if on is not None:
        stmt = stmt.where(Recommendation.run_date == on)
    stmt = stmt.order_by(Recommendation.run_date.desc()).limit(1)
    rec = db.scalars(stmt).first()
    if rec is None:
        raise HTTPException(status_code=404, detail=f"종목 {code} 추천 이력 없음")

    cd = chart(code, rec.run_date)
    box = cd.get("base_box")
    return StockDetailResponse(
        ticker=rec.ticker, name=rec.name, price_provisional=rec.price_provisional,
        grade=rec.grade, final=rec.final,
        candles=[Candle(**c) for c in cd.get("candles", [])],
        high_52w=cd["high_52w"], prior_high=cd["prior_high"],
        base_box=BaseBox(**box) if box else None,
        contributions={
            "s_shin": rec.s_shin, "rvol_confirm": rec.rvol_confirm, "supply_tilt": rec.supply_tilt,
            "regime_mult": rec.regime_mult, "veto": rec.veto, "core": rec.core,
        },
    )
