"""launcher(EXE 진입점) — 단일 인스턴스 가드.

launcher 는 backend 루트 모듈(pythonpath=".")이라 직접 임포트해 검증한다.
무거운 의존(uvicorn/pystray/cloudflared)은 전부 지연 임포트라 임포트만으론 안 뜬다.
"""
import webbrowser

import launcher


def test_second_launch_opens_board_and_exits(tmp_path, monkeypatch):
    # 이미 인스턴스가 떠 있으면: 서버/스케줄러/터널을 새로 띄우지 않고 보드만 연다.
    # 가드가 없으면 두 번째 실행은 포트 충돌로 ~20초 뒤 소리 없이 죽는다(실측).
    monkeypatch.setenv("CBR_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(launcher, "_existing_instance_alive", lambda: True)
    opened = []
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    def boom(*a, **k):
        raise AssertionError("기존 인스턴스가 있으면 서버를 새로 띄우면 안 된다")

    monkeypatch.setattr(launcher.WebServer, "start", boom)

    assert launcher.main() == 0
    assert opened == [launcher.LOCAL_URL]


def test_existing_instance_alive_false_when_port_closed(monkeypatch):
    # 헬스 URL 접속 실패(미기동) → False (첫 실행 경로).
    monkeypatch.setattr(launcher, "LOCAL_URL", "http://127.0.0.1:1")   # 닫힌 포트
    assert launcher._existing_instance_alive() is False
