from datetime import date
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.backtest import get_backtest_runner
from app.main import create_app
from app.store.db import get_db


def test_backtest_calls_runner_with_range(db_session):
    calls = {}

    def fake_runner(start, end):
        calls["start"], calls["end"] = start, end
        return SimpleNamespace(start=start, end=end, n_picks=120, rank_ic=0.031, t_stat=2.4,
                               hit_rate=0.55, avg_return=0.004, note="D-1 서브셋")

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_backtest_runner] = lambda: fake_runner
    client = TestClient(app)

    body = client.get("/backtest?start=2025-01-01&end=2025-12-31").json()
    assert calls["start"] == date(2025, 1, 1)
    assert calls["end"] == date(2025, 12, 31)
    assert body["n_picks"] == 120
    assert body["rank_ic"] == 0.031
    assert body["t_stat"] == 2.4
    assert body["note"] == "D-1 서브셋"
