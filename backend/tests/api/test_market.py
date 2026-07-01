import pandas as pd
import pytest

import app.data.pykrx_client as pykrx_client
from app.api.market import get_market_provider


def _fake_overview():
    return {
        "asof": None,
        "breadth": {"advancers": 12, "decliners": 8, "unchanged": 3,
                    "new_highs": 4, "limit_ups": 2},
        "sectors": [
            {"name": "전기전자", "change_pct": 1.8},
            {"name": "화학", "change_pct": -0.9},
        ],
    }


def test_market_serializes_breadth_and_sectors(client):
    client.app.dependency_overrides[get_market_provider] = lambda: _fake_overview
    body = client.get("/market").json()
    b = body["breadth"]
    assert b["advancers"] == 12
    assert b["decliners"] == 8
    assert b["unchanged"] == 3
    assert b["new_highs"] == 4
    assert b["limit_ups"] == 2
    assert [s["name"] for s in body["sectors"]] == ["전기전자", "화학"]
    assert body["sectors"][0]["change_pct"] == 1.8


def test_market_empty_returns_200_not_500(client):
    # pykrx 결과가 비면 breadth 0집계·sectors 빈 리스트로 200 유지
    empty = {"asof": None,
             "breadth": {"advancers": 0, "decliners": 0, "unchanged": 0,
                         "new_highs": 0, "limit_ups": 0},
             "sectors": []}
    client.app.dependency_overrides[get_market_provider] = lambda: (lambda: empty)
    resp = client.get("/market")
    assert resp.status_code == 200
    body = resp.json()
    assert body["breadth"]["advancers"] == 0
    assert body["sectors"] == []


class _FakeMarketModule:
    """기본 provider 경로용 주입 pykrx 모듈 — 네트워크 없음."""

    def get_nearest_business_day_in_a_week(self, *args, **kw):
        return "20260630"

    def get_market_ohlcv_by_ticker(self, date, market="ALL"):
        return pd.DataFrame(
            {"고가": [100.0, 100.0], "종가": [100.0, 90.0], "등락률": [1.0, -2.0]},
            index=["000660", "005930"],
        )

    def get_index_ohlcv(self, fromdate, todate, index_code):
        if index_code == "1013":
            return pd.DataFrame({"종가": [100.0, 105.0]}, index=["20260629", "20260630"])
        return None


def test_market_uses_default_pykrx_provider(client, monkeypatch):
    # get_market_provider 미오버라이드 → 실제 market_overview 경로. pykrx만 가짜 모듈.
    monkeypatch.setattr(pykrx_client, "_load_pykrx", lambda: _FakeMarketModule())
    resp = client.get("/market")
    assert resp.status_code == 200                     # 500 아님
    body = resp.json()
    assert body["breadth"]["advancers"] == 1           # 등락률 1.0
    assert body["breadth"]["decliners"] == 1           # 등락률 -2.0
    assert body["sectors"][0]["name"] == "전기전자"
    assert body["sectors"][0]["change_pct"] == pytest.approx(5.0)  # 105/100-1
