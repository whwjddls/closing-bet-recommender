import pytest


@pytest.fixture(autouse=True)
def _no_ambient_telegram(monkeypatch):
    """테스트에서 실제 텔레그램 발송 차단.

    app.main 임포트가 backend/.env 를 os.environ 에 주입하므로, 토큰이 설정된 머신에서
    pytest 를 돌리면 run_daily OK 경로 테스트들이 **실제 폰으로 가짜 메시지를 발송**하고
    데스크톱 폴백 검증도 깨진다(실제 발생). 텔레그램 테스트는 token/chat_id 를 명시 주입."""
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)


class FakeClock:
    """주입형 시계 — now()/sleep()로 결정론적 시간 제어."""

    def __init__(self, start: float = 0.0):
        self._t = start
        self.sleeps: list[float] = []

    def now(self) -> float:
        return self._t

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if seconds > 0:
            self._t += seconds

    def advance(self, seconds: float) -> None:
        self._t += seconds


@pytest.fixture
def fake_clock():
    return FakeClock()


@pytest.fixture
def state_dir(tmp_path):
    d = tmp_path / "state"
    d.mkdir()
    return d
