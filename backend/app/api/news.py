from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import NewsItem, NewsResponse

router = APIRouter(tags=["news"])


def get_news_provider() -> Callable:
    """종목 뉴스 제목 공급자(KIS news-title). 테스트는 dependency_overrides 로 주입.
    실제 구현은 호출 시점 지연 임포트 — KIS 네트워크는 provider 호출 때만 발생."""
    def _provider(ticker: str) -> list[dict]:
        from app.data.kis_client import build_default_client
        return build_default_client().get_news_titles(ticker)
    return _provider


@router.get("/news/{ticker}", response_model=NewsResponse)
def get_news(ticker: str, provider: Callable = Depends(get_news_provider)) -> NewsResponse:
    try:
        rows = provider(ticker) or []
    except Exception:                     # KIS 네트워크/크리덴셜 장애 → graceful 빈 응답
        rows = []
    items = [NewsItem(datetime=str(r.get("datetime", "")), title=str(r.get("title", "")))
             for r in rows if r.get("title")]
    return NewsResponse(items=items)
