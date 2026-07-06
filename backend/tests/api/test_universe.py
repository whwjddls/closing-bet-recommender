from datetime import date

from app.store.models import UniverseCache


def _u(ticker, as_of, eligible=True, market="KOSPI"):
    return UniverseCache(ticker=ticker, name=f"N{ticker}", market=market, sec_type="보통주",
                         avg_value_20d=1.2e10, is_managed=False, is_warning=False, is_caution=False,
                         listing_days=500, eligible=eligible, as_of=as_of)


def test_universe_returns_latest_as_of_only(client, db_session):
    db_session.add(_u("000660", date(2026, 6, 29)))     # 과거분
    db_session.add(_u("000660", date(2026, 6, 30)))     # 최신
    db_session.add(_u("005930", date(2026, 6, 30), eligible=False))
    db_session.commit()
    body = client.get("/universe").json()
    assert body["as_of"] == "2026-06-30"
    assert body["total"] == 2
    assert body["eligible_count"] == 1
    tickers = {r["ticker"] for r in body["rows"]}
    assert tickers == {"000660", "005930"}


def test_universe_empty(client):
    body = client.get("/universe").json()
    assert body["as_of"] is None
    assert body["total"] == 0
    assert body["rows"] == []


def test_universe_writer_upsert_then_endpoint_returns_rows(client, db_session):
    """T2: persist_universe_cache 로 선정 유니버스를 적재하면 /universe 가 rows 를 반환한다.
    라이터가 일부 필드(name/sec_type/listing)를 비워도 nullable 로 200 직렬화돼야 한다."""
    from types import SimpleNamespace

    from app.store import final_cache

    bundle = SimpleNamespace(
        run_date=date(2026, 6, 30), universe=["000660", "035720"],
        market_of={"000660": "KOSPI", "035720": "KOSDAQ"},
        avg_value_20d={"000660": 5e10, "035720": 3e10})
    # 벌크 종목명 맵 주입(오프라인). 맵에 없는 종목은 name None 유지.
    saved = final_cache.persist_universe_cache(
        db_session, bundle, names={"000660": "SK하이닉스"})
    db_session.commit()
    assert saved == 2

    body = client.get("/universe").json()
    assert body["as_of"] == "2026-06-30"
    assert body["total"] == 2
    assert body["eligible_count"] == 2                 # 선정 종목 eligible=True
    rows = {r["ticker"]: r for r in body["rows"]}
    assert set(rows) == {"000660", "035720"}
    assert rows["000660"]["market"] == "KOSPI"
    assert rows["000660"]["avg_value_20d"] == 5e10
    assert rows["000660"]["name"] == "SK하이닉스"       # 벌크 맵으로 채움
    assert rows["035720"]["name"] is None              # 맵에 없으면 nullable 유지
