from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ENGINE_URL = "sqlite:///state/closing_bet.db"
engine = create_engine(ENGINE_URL, future=True)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """스키마 생성(멱등). 파일 기반 sqlite 는 상위 디렉터리를 먼저 보장한다
    (신규 배포 시 state/ 부재로 인한 스타트업 실패 방지)."""
    from app.store.models import Base

    db_file = engine.url.database
    if db_file and db_file != ":memory:":
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
