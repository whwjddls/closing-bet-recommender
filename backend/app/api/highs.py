from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import HighItem, HighsResponse

router = APIRouter(tags=["highs"])


def get_highs_provider() -> Callable:
    """신고가 근접 '주식' 공급자 = KIS near-new-highlow ∩ KRX 상장주식.

    KIS 랭킹은 ETF·ETN·채권펀드를 섞어 주는데(실측 2026-07-03), 이들은 전략
    대상이 아니고 pykrx 주식 API가 지원하지 않아 클릭 시 빈 화면이 된다 → 필터.
    테스트는 dependency_overrides 로 주입. 지연 임포트 — 네트워크는 호출 때만."""
    def _provider() -> list[dict]:
        from app.data.kis_client import build_default_client
        from app.data.pykrx_client import filter_listed_stocks
        return filter_listed_stocks(build_default_client().get_near_new_highs())
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
