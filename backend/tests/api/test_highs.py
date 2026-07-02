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
