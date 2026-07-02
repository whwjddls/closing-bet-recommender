from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import HighItem, HighsResponse

router = APIRouter(tags=["highs"])


def get_highs_provider() -> Callable:
    """신고가 근접 종목 공급자(KIS near-new-highlow). 테스트는 dependency_overrides 로 주입.
    실제 구현은 호출 시점 지연 임포트 — KIS 네트워크는 provider 호출 때만 발생."""
    def _provider() -> list[dict]:
        from app.data.kis_client import build_default_client
        return build_default_client().get_near_new_highs()
    return _provider


@router.get("/highs", response_model=HighsResponse)
def get_highs(provider: Callable = Depends(get_highs_provider)) -> HighsResponse:
    try:
        rows = provider() or []
    except Exception:                     # KIS 네트워크/크리덴셜 장애 → graceful 빈 응답
        rows = []
    items = [HighItem(ticker=r.get("ticker", ""), name=r.get("name", ""))
             for r in rows if r.get("ticker")]
    return HighsResponse(items=items)
