from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool

import app.store.db as db
from app.main import create_app

EXPECTED_TABLES = {
    "recommendations", "performance", "runs", "universe_cache",
    "regime_snapshots", "volume_snapshots", "corp_code_map",
}


def test_app_lifespan_initializes_db_schema(monkeypatch):
    # 프로덕션 부팅(FastAPI lifespan startup)에서 init_db() 가 호출돼 스키마가
    # 생성되는지 — init_db 데드코드(스타트업 미호출) 회귀 방지.
    test_engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    monkeypatch.setattr(db, "engine", test_engine)

    with TestClient(create_app()):          # 컨텍스트 진입 → startup(lifespan) 실행
        pass

    tables = set(inspect(test_engine).get_table_names())
    assert EXPECTED_TABLES <= tables
