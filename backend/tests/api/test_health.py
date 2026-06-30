from datetime import date, datetime

from app.store.models import Run


def test_health_down_when_no_runs(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DOWN"                 # 00 §5: 대문자
    assert body["reason"]                           # 사유 필드(detail 아님)
    assert body["last_run_date"] is None
    assert body["board_published"] is False
    assert body["kis_coverage_pct"] == 0.0


def test_health_ok_when_latest_run_published(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime(2026, 6, 30, 15, 20),
                       finished_at=datetime(2026, 6, 30, 15, 20, 14), status="OK",
                       kis_coverage_pct=92.0, board_published=True, session_type="정규", reason=None))
    db_session.commit()
    body = client.get("/health").json()
    assert body["status"] == "OK"
    assert body["last_run_date"] == "2026-06-30"
    assert body["kis_coverage_pct"] == 92.0
    assert body["board_published"] is True


def test_health_degraded_when_unpublished(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 29), started_at=datetime(2026, 6, 29, 15, 20),
                       finished_at=datetime(2026, 6, 29, 15, 20, 5), status="UNPUBLISHED",
                       kis_coverage_pct=61.0, board_published=False, session_type="정규",
                       reason="커버리지 61% < 70%"))
    db_session.commit()
    body = client.get("/health").json()
    assert body["status"] == "DEGRADED"
    assert "커버리지" in body["reason"]               # 00 §5: reason
