from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import Breadth, MarketResponse, SectorChange

router = APIRouter(tags=["market"])


def get_market_provider() -> Callable:
    """시장 개요 데이터 공급자(breadth·sectors). 테스트는 dependency_overrides 로 주입.
    실제 구현은 호출 시점 지연 임포트 — pykrx 네트워크는 provider 호출 때만 발생."""
    def _provider() -> dict:
        from app.data.pykrx_client import market_overview
        return market_overview()
    return _provider


@router.get("/market", response_model=MarketResponse)
def get_market(provider: Callable = Depends(get_market_provider)) -> MarketResponse:
    data = provider()
    b = data.get("breadth") or {}
    breadth = Breadth(
        advancers=b.get("advancers", 0), decliners=b.get("decliners", 0),
        unchanged=b.get("unchanged", 0), new_highs=b.get("new_highs", 0),
        limit_ups=b.get("limit_ups", 0),
    )
    sectors = [SectorChange(**s) for s in data.get("sectors", [])]
    return MarketResponse(breadth=breadth, sectors=sectors)
