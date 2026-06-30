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
