from datetime import date, datetime

from app.api.stock import get_chart_provider
from app.store.models import Recommendation


def _rec(d, **kw):
    base = dict(run_date=d, ticker="000660", name="SK하이닉스", market="KOSPI", rank=1,
                price_provisional=24500.0, buy_price_provisional=24500.0, buy_price_final=None,
                s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03, regime_mult=1.0, veto=1,
                core=1.12, final=1.12, grade="S", near_252=1.02, near_60=1.04, rvol=2.5,
                target_price=25200.0, stop_price=23800.0, spark=[1.0, 2.0, 3.0], base_flag=True,
                provisional_flag=True, created_at=datetime.now())
    base.update(kw)
    return Recommendation(**base)


def _fake_chart(code, run_date):
    return {
        "candles": [
            {"date": "2026-06-26", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000},
            {"date": "2026-06-29", "open": 104.0, "high": 110.0, "low": 103.0, "close": 109.0, "volume": 2000},
        ],
        "high_52w": 120.0,
        "prior_high": 108.0,
        "base_box": {"start": "2026-06-01", "end": "2026-06-20", "low": 95.0, "high": 107.0},
    }


def test_stock_serializes_candles_high_box_and_contributions(client, db_session):
    client.app.dependency_overrides[get_chart_provider] = lambda: _fake_chart
    db_session.add(_rec(date(2026, 6, 29), core=0.7, final=0.7, grade="A"))
    db_session.add(_rec(date(2026, 6, 30), core=1.12, final=1.12, grade="S"))
    db_session.commit()
    body = client.get("/stock/000660").json()
    assert body["grade"] == "S"                        # 최신 run_date
    assert body["final"] == 1.12
    # 00 §5: candles/high_52w/prior_high/base_box 직렬화
    assert len(body["candles"]) == 2
    assert body["candles"][0]["close"] == 104.0
    assert body["high_52w"] == 120.0
    assert body["prior_high"] == 108.0
    assert body["base_box"]["high"] == 107.0
    # contributions {s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}
    contrib = body["contributions"]
    assert contrib["s_shin"] == 1.16
    assert contrib["rvol_confirm"] == 0.93
    assert contrib["core"] == 1.12


def test_stock_specific_date_query(client, db_session):
    client.app.dependency_overrides[get_chart_provider] = lambda: _fake_chart
    db_session.add(_rec(date(2026, 6, 29), core=0.7, final=0.7, grade="A"))
    db_session.add(_rec(date(2026, 6, 30)))
    db_session.commit()
    body = client.get("/stock/000660?on=2026-06-29").json()
    assert body["grade"] == "A"
    assert body["final"] == 0.7


def test_stock_404_when_missing(client):
    # 차트 공급자 미오버라이드 — 404 가 차트 호출보다 먼저라 지연 임포트도 일어나지 않음
    assert client.get("/stock/999999").status_code == 404
