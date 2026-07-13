"""corp_code_map 스토어 — DART corpCode.xml 시딩 결과 영속화.

빈 맵은 전 종목 veto=0(fail-closed) → 보드 영구 공백을 뜻하므로, 시딩은
merge-upsert 로 기존 매핑을 보존하고(다운로드 실패 시에도 축소 금지)
``count_mapped`` 로 매핑 수를 노출해 premarket 이 fail-closed 판정에 쓴다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.store.models import CorpCodeMap


def upsert_corp_code_map(db: Session, entries: Iterable[Tuple[str, str, str]]) -> int:
    """``[(corp_code, ticker, name)]`` merge-upsert(corp_code PK). 처리 건수 반환."""
    now = datetime.now()
    count = 0
    for corp_code, ticker, name in entries:
        db.merge(CorpCodeMap(corp_code=corp_code, ticker=ticker, name=name, updated_at=now))
        count += 1
    return count


def count_mapped(db: Session) -> int:
    """ticker 매핑이 있는 행 수 — 0 이면 veto 전멸(전 종목 차단) 신호."""
    return db.scalar(
        select(func.count()).select_from(CorpCodeMap)
        .where(CorpCodeMap.ticker.is_not(None), CorpCodeMap.ticker != "")
    ) or 0
