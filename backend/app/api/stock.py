from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import BaseBox, Candle, OvernightGap, StockDetailResponse, Supply5d
from app.store.db import get_db
from app.store.models import Recommendation

router = APIRouter(tags=["stock"])


def get_chart_provider() -> Callable:
    """차트 데이터 공급자(캔들·52주최고·직전고점·베이스박스·오버나잇갭·5일수급).
    테스트는 dependency_overrides 로 주입. 실제 구현은 호출 시점 지연 임포트라
    404(rec 없음) 경로에선 임포트가 일어나지 않는다."""
    def _provider(code: str, run_date: date) -> dict:
        from app.data.pykrx_client import get_stock_chart, overnight_gap_stats, supply_5d
        data = get_stock_chart(code, run_date)
        data["overnight_gap"] = overnight_gap_stats(code, run_date)  # None이면 콜드스타트
        data["supply_5d"] = supply_5d(code, run_date)               # None이면 미가용
        return data
    return _provider


@router.get("/stock/{code}", response_model=StockDetailResponse)
def get_stock(code: str, on: date | None = None, db: Session = Depends(get_db),
              chart: Callable = Depends(get_chart_provider)) -> StockDetailResponse:
    stmt = select(Recommendation).where(Recommendation.ticker == code)
    if on is not None:
        stmt = stmt.where(Recommendation.run_date == on)
    stmt = stmt.order_by(Recommendation.run_date.desc()).limit(1)
    rec = db.scalars(stmt).first()

    # 추천 이력이 없어도(신고가 근접 위젯 등에서 진입) 참고 조회 허용 —
    # 차트·하룻밤 변동·5일 수급은 추천과 무관하게 계산 가능. 추천 전용 필드만 None.
    cd = chart(code, rec.run_date if rec is not None else (on or date.today()))
    box = cd.get("base_box")
    gap = cd.get("overnight_gap")
    supply = cd.get("supply_5d")
    candles = [Candle(**c) for c in cd.get("candles", [])]

    if rec is None:
        last_close = candles[-1].close if candles else 0.0
        return StockDetailResponse(
            ticker=code, name=code, price_provisional=last_close,
            grade=None, final=None, candles=candles,
            high_52w=cd["high_52w"], prior_high=cd["prior_high"],
            base_box=BaseBox(**box) if box else None,
            overnight_gap=OvernightGap(**gap) if gap else None,
            supply_5d=Supply5d(**supply) if supply else None,
            contributions={})

    return StockDetailResponse(
        ticker=rec.ticker, name=rec.name, price_provisional=rec.price_provisional,
        grade=rec.grade, final=rec.final,
        candles=candles,
        high_52w=cd["high_52w"], prior_high=cd["prior_high"],
        base_box=BaseBox(**box) if box else None,
        overnight_gap=OvernightGap(**gap) if gap else None,
        supply_5d=Supply5d(**supply) if supply else None,
        contributions={
            "s_shin": rec.s_shin, "rvol_confirm": rec.rvol_confirm, "supply_tilt": rec.supply_tilt,
            "regime_mult": rec.regime_mult, "veto": rec.veto, "core": rec.core,
        },
    )
