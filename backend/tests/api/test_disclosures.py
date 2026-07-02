from app.api.disclosures import get_disclosures_provider


def _row(date, kind="희석", ticker="005930", name="삼성전자", title="유상증자결정"):
    return {"date": date, "ticker": ticker, "name": name, "kind": kind, "title": title}


def test_disclosures_serializes_items(client):
    rows = [_row("20260629"),
            _row("20260628", kind="배당", ticker="000660", name="SK하이닉스",
                 title="현금배당결정")]
    client.app.dependency_overrides[get_disclosures_provider] = \
        lambda: (lambda since: rows)
    body = client.get("/disclosures").json()
    assert len(body["items"]) == 2
    assert body["items"][0] == {"date": "20260629", "ticker": "005930",
                                "name": "삼성전자", "kind": "희석",
                                "title": "유상증자결정"}
    assert body["items"][1]["kind"] == "배당"


def test_disclosures_sorted_desc_and_limited_to_30(client):
    rows = [_row(f"202606{day:02d}") for day in range(1, 40)]     # 39건, 뒤섞기 전
    client.app.dependency_overrides[get_disclosures_provider] = \
        lambda: (lambda since: rows)
    items = client.get("/disclosures").json()["items"]
    assert len(items) == 30                                       # 최신 30건만
    dates = [it["date"] for it in items]
    assert dates == sorted(dates, reverse=True)                   # 최신순
    assert dates[0] == "20260639"                                 # 가장 큰 date 우선


def test_disclosures_graceful_empty_on_provider_error(client):
    def _boom(since):
        raise ConnectionError("DART down")

    client.app.dependency_overrides[get_disclosures_provider] = lambda: _boom
    resp = client.get("/disclosures")
    assert resp.status_code == 200                                # 500 아님
    assert resp.json()["items"] == []


def test_disclosures_default_provider_no_network(client):
    # 미오버라이드(실 provider) → 200 + items 는 list. 크래시 없음.
    # (크리덴셜 미설정이면 [], .env 에 DART 키 있으면 실제 공시 목록 — 둘 다 정상.)
    resp = client.get("/disclosures")
    assert resp.status_code == 200
    assert isinstance(resp.json()["items"], list)
