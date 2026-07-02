import threading

import pytest

from app.api import run as run_module


@pytest.fixture(autouse=True)
def _reset_run_state():
    # 모듈 레벨 상태를 매 테스트마다 초기화(테스트 간 오염 방지).
    run_module._state.update(
        running=False, last_result=None, last_error=None, finished_at=None)
    yield
    run_module._state.update(
        running=False, last_result=None, last_error=None, finished_at=None)


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


def test_post_run_starts_and_status_transitions_to_finished(client, monkeypatch):
    release = threading.Event()

    def fake_run_daily():
        release.wait(timeout=2.0)       # 테스트가 풀어줄 때까지 running 유지
        return "OK"

    monkeypatch.setattr(run_module, "_invoke_run_daily", fake_run_daily)

    resp = client.post("/run")
    assert resp.status_code == 200
    assert resp.json() == {"status": "started"}

    # 실행 중 관찰
    assert _wait(lambda: client.get("/run/status").json()["running"] is True)
    status = client.get("/run/status").json()
    assert status["running"] is True
    assert status["last_result"] is None

    release.set()                       # 런 완료 허용
    assert _wait(lambda: client.get("/run/status").json()["running"] is False)
    finished = client.get("/run/status").json()
    assert finished["running"] is False
    assert finished["last_result"] == "OK"
    assert finished["last_error"] is None
    assert finished["finished_at"] is not None


def test_second_post_while_running_returns_already_running(client, monkeypatch):
    release = threading.Event()

    def fake_run_daily():
        release.wait(timeout=2.0)
        return "OK"

    monkeypatch.setattr(run_module, "_invoke_run_daily", fake_run_daily)

    assert client.post("/run").json() == {"status": "started"}
    assert _wait(lambda: client.get("/run/status").json()["running"] is True)
    assert client.post("/run").json() == {"status": "already_running"}
    release.set()
    assert _wait(lambda: client.get("/run/status").json()["running"] is False)


def test_run_exception_sets_last_error_and_running_false(client, monkeypatch):
    def boom():
        raise RuntimeError("pipeline exploded")

    monkeypatch.setattr(run_module, "_invoke_run_daily", boom)

    assert client.post("/run").json() == {"status": "started"}
    assert _wait(lambda: client.get("/run/status").json()["finished_at"] is not None)
    status = client.get("/run/status").json()
    assert status["running"] is False
    assert status["last_result"] is None
    assert status["last_error"] == "pipeline exploded"


def test_none_result_maps_to_skipped(client, monkeypatch):
    monkeypatch.setattr(run_module, "_invoke_run_daily", lambda: None)

    assert client.post("/run").json() == {"status": "started"}
    assert _wait(lambda: client.get("/run/status").json()["finished_at"] is not None)
    status = client.get("/run/status").json()
    assert status["running"] is False
    assert status["last_result"] == "SKIPPED"
    assert status["last_error"] is None
