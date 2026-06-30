from datetime import date, datetime

from app.store.models import Recommendation, RegimeSnapshot, Run


def _rec(**kw):
    base = dict(run_date=date(2026, 6, 30), ticker="000660", name="SK하이닉스", market="KOSPI",
                rank=1, price_provisional=24500.0, buy_price_provisional=24500.0, buy_price_final=None,
                s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03, regime_mult=1.0, veto=1,
                core=1.12, final=1.12, grade="S", near_252=1.02, near_60=1.04, rvol=2.5,
                target_price=25200.0, stop_price=23800.0, spark=[1.0, 2.0, 3.0], base_flag=True,
                provisional_flag=True, created_at=datetime.now())
    base.update(kw)
    return Recommendation(**base)


def _published_run(d=date(2026, 6, 30), coverage=90.0):
    return Run(run_date=d, started_at=datetime.now(), finished_at=datetime.now(), status="OK",
               kis_coverage_pct=coverage, board_published=True, session_type="정규", reason=None)


def _regime(market="KOSPI", regime_mult=1.0):
    return RegimeSnapshot(run_date=date(2026, 6, 30), market=market, index_level=2700.0,
                          ma5=2680.0, ma5_prev=2670.0, cond_a=True, cond_b=True, regime_mult=regime_mult)


def test_recommendations_returns_ranked_rows_and_regime_dict(client, db_session):
    db_session.add(_published_run())
    db_session.add(_rec(rank=2, ticker="005930", name="삼성전자", core=0.55, final=0.55, grade="B"))
    db_session.add(_rec(rank=1))
    db_session.add(_regime())
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["run_date"] == "2026-06-30"
    assert body["session_type"] == "정규"
    assert body["data_available"] is True
    assert body["kis_coverage_pct"] == 90.0
    assert [r["rank"] for r in body["recommendations"]] == [1, 2]   # rank 오름차순
    assert body["recommendations"][0]["grade"] == "S"
    assert body["recommendations"][0]["score"] == 1.12             # score = final
    # 00 §5: regimes 는 dict[str, RegimeInfo] (시장 키)
    assert isinstance(body["regimes"], dict)
    assert body["regimes"]["KOSPI"]["regime_mult"] == 1.0


def test_recommendations_response_schema_has_spark_and_base_flag(client, db_session):
    """00 §5 정본: RecommendationRow 에 spark/base_flag/score/exit_label/badges 존재."""
    db_session.add(_published_run())
    db_session.add(_rec(rank=1))
    db_session.add(_regime())
    db_session.commit()
    row = client.get("/recommendations/2026-06-30").json()["recommendations"][0]
    assert "spark" in row and isinstance(row["spark"], list) and row["spark"] == [1.0, 2.0, 3.0]
    assert "base_flag" in row and row["base_flag"] is True
    assert row["score"] == 1.12                                    # = final
    assert row["exit_label"].startswith("익일 오전 VWAP")
    assert "badges" in row and isinstance(row["badges"], list)


def test_recommendations_empty_board_keeps_data_available(client, db_session):
    """저레짐으로 추천 0이어도 data_available=true (00 §5)."""
    db_session.add(_published_run(coverage=88.0))
    db_session.add(_regime(market="KOSPI", regime_mult=0.0))
    db_session.add(_regime(market="KOSDAQ", regime_mult=0.0))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["data_available"] is True
    assert body["recommendations"] == []
    assert body["regimes"]["KOSPI"]["regime_mult"] == 0.0


def test_recommendations_unpublished_run_has_no_rows(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime.now(), finished_at=datetime.now(),
                       status="UNPUBLISHED", kis_coverage_pct=61.0, board_published=False,
                       session_type="정규", reason="커버리지 61% < 70%"))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["recommendations"] == []
    assert body["kis_coverage_pct"] == 61.0
    assert body["data_available"] is True       # 커버리지>0 → KIS 데이터는 수신됨
