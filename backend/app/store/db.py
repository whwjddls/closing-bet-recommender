from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings

# 절대경로(_BACKEND_ROOT/state 기반)로 고정 — 실행 cwd(서버 vs 스크립트)에 따라
# 다른 .db 파일을 보던 문제 방지. CBR_DB_PATH 로 override 가능.
_DB_PATH = get_settings().db_path
ENGINE_URL = f"sqlite:///{_DB_PATH.as_posix()}"
engine = create_engine(ENGINE_URL, future=True)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, expire_on_commit=False, future=True)

BUSY_TIMEOUT_MS = 5000


@event.listens_for(engine, "connect")
def _sqlite_concurrency_pragmas(dbapi_connection, _record) -> None:
    """WAL + busy_timeout — 스캔(쓰기)과 UI 조회(읽기)가 동시에 일어난다.

    기본 저널 모드에서는 쓰기 트랜잭션이 읽기를 막아 UI 가 'database is locked' 로
    깨질 수 있다. WAL 은 읽기와 쓰기를 동시에 허용한다(스케줄러 잡이 도는 동안에도
    보드가 열려야 한다)."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    finally:
        cursor.close()


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_columns(target_engine) -> None:
    """경량 자동 마이그레이션 — 모델에 nullable 컬럼이 추가돼도 기존 sqlite 테이블이
    깨지지 않게 누락 컬럼을 ALTER TABLE ADD COLUMN 으로 보강한다(멱등).
    create_all 은 기존 테이블에 컬럼을 추가하지 않아, 과거 spark/base_flag ·
    exp_close/supply_today 추가 때 구 DB 조회가 500 을 냈던 재발 방지."""
    from app.store.models import Base

    insp = inspect(target_engine)
    with target_engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                coltype = col.type.compile(target_engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {coltype}'))


def init_db() -> None:
    """스키마 생성(멱등). 파일 기반 sqlite 는 상위 디렉터리를 먼저 보장한다
    (신규 배포 시 state/ 부재로 인한 스타트업 실패 방지)."""
    from app.store.models import Base

    db_file = engine.url.database
    if db_file and db_file != ":memory:":
        Path(db_file).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _ensure_columns(engine)          # 기존 테이블 누락 컬럼 보강(구 DB 호환)
