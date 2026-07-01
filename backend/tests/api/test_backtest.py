from datetime import date
from types import SimpleNamespace

import pandas as pd
from fastapi.testclient import TestClient

import app.data.pykrx_client as pykrx_client
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


class _FakeBacktestPykrx:
    """백테스트 로더용 주입형 가짜 pykrx 모듈 — 네트워크 없음."""

    def get_market_ticker_list(self, date, market="ALL"):
        return ["000660", "005930"]

    def get_market_ohlcv(self, fromdate, todate, ticker):
        idx = pd.to_datetime(["2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01"])
        return pd.DataFrame(
            {
                "시가": [100.0, 101.0, 102.0, 103.0],
                "고가": [105.0, 106.0, 107.0, 108.0],
                "저가": [99.0, 100.0, 101.0, 102.0],
                "종가": [104.0, 105.0, 106.0, 107.0],
                "거래량": [1000, 1100, 1200, 1300],
                "거래대금": [1e9, 1.1e9, 1.2e9, 1.3e9],
            },
            index=idx,
        )


def test_backtest_default_runner_uses_pykrx_loaders(db_session, monkeypatch):
    # get_backtest_runner 미오버라이드 → 실 기본 러너(pykrx 기반 로더 바인딩) 구동.
    # 외부 pykrx 네트워크만 가짜 모듈로 대체(로더 미주입→500 회귀 방지).
    monkeypatch.setattr(pykrx_client, "_load_pykrx", lambda: _FakeBacktestPykrx())

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    resp = client.get("/backtest?start=2026-06-29&end=2026-06-30")
    assert resp.status_code == 200                      # 500 아님
    body = resp.json()
    assert body["start"] == "2026-06-29"
    assert body["end"] == "2026-06-30"
    assert body["n_picks"] == 4                         # 2종목 × 2거래일, VWAP 프록시 존재
    # 프로덕션 membership 소스 미확보 → survivorship 파생 False → DOWNSCOPE(조용한 통과 금지)
    assert "DOWNSCOPE" in body["note"]
