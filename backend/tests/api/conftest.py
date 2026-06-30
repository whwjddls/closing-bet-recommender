import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import create_app
from app.store.db import get_db
from app.store.models import Base


@pytest.fixture
def db_session():
    # StaticPool: 단일 공유 커넥션 — TestClient 요청 스레드와 create_all이
    # 같은 인메모리 DB를 보도록 보장(스레드별 분리 인메모리 DB 방지).
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False},
        poolclass=StaticPool)
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)
