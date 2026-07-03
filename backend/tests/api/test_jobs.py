"""수동 잡 버튼 API(/jobs/prefetch·/jobs/scoring) — run.py(스캔 버튼)와 동일 계약."""
import threading
from datetime import datetime

import pytest

from app.api import jobs as jobs_module


@pytest.fixture(autouse=True)
def _reset_job_states():
    # 모듈 레벨 상태를 매 테스트마다 초기화(테스트 간 오염 방지).
    for state in jobs_module._states.values():
        state.update(running=False, last_result=None, last_error=None,
                     finished_at=None, started_at=None, started_ts=None)
    yield
    for state in jobs_module._states.values():
        state.update(running=False, last_result=None, last_error=None,
                     finished_at=None, started_at=None, started_ts=None)


def _wait(pred, timeout=2.0):
    done = threading.Event()

    def _spin():
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if pred():
                done.set()
                return
            time.sleep(0.005)
    t = threading.Thread(target=_spin)
    t.start()
    t.join()
    return done.is_set()


def test_prefetch_starts_and_finishes_ok(client, monkeypatch):
    release = threading.Event()

    def fake_prefetch():
        release.wait(timeout=2.0)
        return "OK"

    monkeypatch.setattr(jobs_module, "_invoke_prefetch", fake_prefetch)

    resp = client.post("/jobs/prefetch")
    assert resp.status_code == 200
    assert resp.json() == {"status": "started", "reason": None}

    assert _wait(lambda: client.get("/jobs/prefetch/status").json()["running"] is True)
    release.set()
    assert _wait(lambda: client.get("/jobs/prefetch/status").json()["running"] is False)
    finished = client.get("/jobs/prefetch/status").json()
    assert finished["last_result"] == "OK"
    assert finished["last_error"] is None
    assert finished["finished_at"] is not None


def test_prefetch_second_post_while_running_returns_already_running(client, monkeypatch):
    release = threading.Event()

    def fake_prefetch():
        release.wait(timeout=2.0)
        return "OK"

    monkeypatch.setattr(jobs_module, "_invoke_prefetch", fake_prefetch)

    assert client.post("/jobs/prefetch").json()["status"] == "started"
    assert _wait(lambda: client.get("/jobs/prefetch/status").json()["running"] is True)
    assert client.post("/jobs/prefetch").json()["status"] == "already_running"
    release.set()
    assert _wait(lambda: client.get("/jobs/prefetch/status").json()["running"] is False)


def test_prefetch_exception_sets_last_error(client, monkeypatch):
    def boom():
        raise RuntimeError("KRX outage")

    monkeypatch.setattr(jobs_module, "_invoke_prefetch", boom)

    assert client.post("/jobs/prefetch").json()["status"] == "started"
    assert _wait(lambda: client.get("/jobs/prefetch/status").json()["finished_at"] is not None)
    status = client.get("/jobs/prefetch/status").json()
    assert status["running"] is False
    assert status["last_error"] == "KRX outage"


def test_prefetch_none_maps_to_skipped(client, monkeypatch):
    # 비거래일 → run_premarket()이 None 반환 → SKIPPED
    monkeypatch.setattr(jobs_module, "_invoke_prefetch", lambda: None)
    assert client.post("/jobs/prefetch").json()["status"] == "started"
    assert _wait(lambda: client.get("/jobs/prefetch/status").json()["finished_at"] is not None)
    assert client.get("/jobs/prefetch/status").json()["last_result"] == "SKIPPED"


def test_scoring_rejected_before_10am(client, monkeypatch):
    # 09:00–10:00 VWAP 창이 끝나기 전 채점 → 부분 VWAP 오채점·영구 고착이라 거부.
    monkeypatch.setattr(jobs_module, "_now",
                        lambda: datetime(2026, 7, 6, 9, 30, 0))
    body = client.post("/jobs/scoring").json()
    assert body["status"] == "rejected"
    assert "10시" in body["reason"]
    # 잡이 시작되지 않았어야 한다
    assert client.get("/jobs/scoring/status").json()["running"] is False


def test_scoring_runs_after_10am_and_reports_count(client, monkeypatch):
    monkeypatch.setattr(jobs_module, "_now",
                        lambda: datetime(2026, 7, 6, 10, 5, 0))
    monkeypatch.setattr(jobs_module, "_invoke_scoring", lambda: 3)

    assert client.post("/jobs/scoring").json()["status"] == "started"
    assert _wait(lambda: client.get("/jobs/scoring/status").json()["finished_at"] is not None)
    status = client.get("/jobs/scoring/status").json()
    assert status["running"] is False
    assert status["last_result"] == "SCORED:3"


def test_scoring_none_maps_to_skipped(client, monkeypatch):
    # 휴장일 → run_scoring()이 None 반환 → SKIPPED
    monkeypatch.setattr(jobs_module, "_now",
                        lambda: datetime(2026, 7, 5, 11, 0, 0))
    monkeypatch.setattr(jobs_module, "_invoke_scoring", lambda: None)
    assert client.post("/jobs/scoring").json()["status"] == "started"
    assert _wait(lambda: client.get("/jobs/scoring/status").json()["finished_at"] is not None)
    assert client.get("/jobs/scoring/status").json()["last_result"] == "SKIPPED"
