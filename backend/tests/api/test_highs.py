from app.api.highs import get_highs_provider


def test_highs_serializes_items(client):
    rows = [{"ticker": "000660", "name": "SK하이닉스"},
            {"ticker": "005930", "name": "삼성전자"}]
    client.app.dependency_overrides[get_highs_provider] = lambda: (lambda: rows)
    body = client.get("/highs").json()
    assert [i["ticker"] for i in body["items"]] == ["000660", "005930"]
    assert body["items"][0]["name"] == "SK하이닉스"


def test_highs_empty_returns_200(client):
    client.app.dependency_overrides[get_highs_provider] = lambda: (lambda: [])
    resp = client.get("/highs")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_highs_provider_failure_returns_empty_200(client):
    def _boom():
        raise ConnectionError("KIS outage")
    client.app.dependency_overrides[get_highs_provider] = lambda: _boom
    resp = client.get("/highs")
    assert resp.status_code == 200                 # graceful — 500 아님
    assert resp.json()["items"] == []


import datetime as dt

import app.data.kis_client as kis_client
import app.data.pykrx_client as pykrx_client


def test_default_provider_filters_non_stocks(monkeypatch):
    # 기본 provider = KIS near-new-highlow ∩ KRX 상장주식. 두 외부 IO 모두 스텁.
    class _StubKis:
        def get_near_new_highs(self):
            return [{"ticker": "005930", "name": "삼성전자"},
                    {"ticker": "000117", "name": "어떤채권ETF"}]

    monkeypatch.setattr(kis_client, "build_default_client", lambda: _StubKis())
    day_s = (dt.date.today()).strftime("%Y%m%d")
    pykrx_client._LISTED_CACHE[day_s] = frozenset({"005930"})
    try:
        rows = get_highs_provider()()
    finally:
        pykrx_client._LISTED_CACHE.clear()
    assert [r["ticker"] for r in rows] == ["005930"]     # ETF(000117) 제거됨
