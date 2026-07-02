from app.api.news import get_news_provider


def test_news_serializes_items(client):
    rows = [{"datetime": "2026-07-01 09:30", "title": "SK하이닉스 신고가"},
            {"datetime": "2026-07-01 14:30", "title": "삼성전자 실적"}]
    client.app.dependency_overrides[get_news_provider] = lambda: (lambda t: rows)
    body = client.get("/news/000660").json()
    assert [i["title"] for i in body["items"]] == ["SK하이닉스 신고가", "삼성전자 실적"]
    assert body["items"][0]["datetime"] == "2026-07-01 09:30"


def test_news_passes_ticker_to_provider(client):
    seen = {}

    def _provider(ticker):
        seen["ticker"] = ticker
        return []

    client.app.dependency_overrides[get_news_provider] = lambda: _provider
    client.get("/news/005930")
    assert seen["ticker"] == "005930"


def test_news_empty_returns_200(client):
    client.app.dependency_overrides[get_news_provider] = lambda: (lambda t: [])
    resp = client.get("/news/000660")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_news_provider_failure_returns_empty_200(client):
    def _boom(ticker):
        raise ConnectionError("KIS outage")

    client.app.dependency_overrides[get_news_provider] = lambda: _boom
    resp = client.get("/news/000660")
    assert resp.status_code == 200                 # graceful — 500 아님
    assert resp.json()["items"] == []
