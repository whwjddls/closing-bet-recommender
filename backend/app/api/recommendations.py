from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import RecommendationRow, RecommendationsResponse, RegimeInfo
from app.store.db import get_db
from app.store.models import Recommendation, RegimeSnapshot, Run

router = APIRouter(tags=["recommendations"])


def _to_row(rec: Recommendation) -> RecommendationRow:
    # 00 §5 RecommendationRow: score=final, grade=core 기준(저장값), spark/base_flag 포함.
    # 배지는 프런트 deriveBadges 가 신호 필드에서 단일 산출한다(백엔드 미직렬화).
    return RecommendationRow(
        rank=rec.rank, ticker=rec.ticker, name=rec.name, market=rec.market,
        price_provisional=rec.price_provisional, buy_price_provisional=rec.buy_price_provisional,
        buy_price_final=rec.buy_price_final, target_price=rec.target_price, stop_price=rec.stop_price,
        score=rec.final, grade=rec.grade,
        near_252=rec.near_252, near_60=rec.near_60, rvol=rec.rvol,
        s_shin=rec.s_shin, rvol_confirm=rec.rvol_confirm, supply_tilt=rec.supply_tilt,
        regime_mult=rec.regime_mult, veto=rec.veto,
        spark=rec.spark or [], base_flag=rec.base_flag, provisional_flag=rec.provisional_flag,
    )


@router.get("/recommendations/{run_date}", response_model=RecommendationsResponse)
def get_recommendations(run_date: date, db: Session = Depends(get_db)) -> RecommendationsResponse:
    run = db.get(Run, run_date)
    recs = db.scalars(
        select(Recommendation).where(Recommendation.run_date == run_date).order_by(Recommendation.rank)
    ).all()
    regime_rows = db.scalars(
        select(RegimeSnapshot).where(RegimeSnapshot.run_date == run_date)
    ).all()
    regimes = {
        rg.market: RegimeInfo(market=rg.market, index_level=rg.index_level, ma5=rg.ma5,
                              regime_mult=rg.regime_mult, cond_a=rg.cond_a, cond_b=rg.cond_b)
        for rg in regime_rows
    }
    coverage = (run.kis_coverage_pct if run else None) or 0.0
    return RecommendationsResponse(
        run_date=run_date.isoformat(),
        session_type=run.session_type if run else None,
        data_available=coverage > 0.0,
        kis_coverage_pct=coverage,
        regimes=regimes,
        recommendations=[_to_row(r) for r in recs],
    )
