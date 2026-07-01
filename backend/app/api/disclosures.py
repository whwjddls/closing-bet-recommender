from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import Disclosure, DisclosuresResponse

router = APIRouter(tags=["disclosures"])

DISCLOSURE_LOOKBACK_DAYS = 14           # 최근 공시 조회 창(달력일)
DISCLOSURE_LIMIT = 30                   # 응답 최대 건수(최신 N)


def get_disclosures_provider() -> Callable:
    """최근 희석/배당 공시 공급자. 테스트는 dependency_overrides 로 주입.
    실 구현은 호출 시점 지연 임포트 — DART 네트워크는 provider 호출 때만 발생."""
    def _provider(since: str) -> list[dict]:
        from app.data.dart_client import DISCLOSURE_KINDS, recent_disclosures
        return recent_disclosures(since, DISCLOSURE_KINDS)
    return _provider


@router.get("/disclosures", response_model=DisclosuresResponse)
def get_disclosures(
        provider: Callable = Depends(get_disclosures_provider)) -> DisclosuresResponse:
    since = (date.today() - timedelta(days=DISCLOSURE_LOOKBACK_DAYS)).strftime("%Y%m%d")
    try:
        rows = provider(since)
    except Exception:                                   # noqa: BLE001  (DART 장애 graceful)
        rows = []
    rows = sorted(rows, key=lambda r: r.get("date", ""), reverse=True)[:DISCLOSURE_LIMIT]
    return DisclosuresResponse(items=[Disclosure(**r) for r in rows])
