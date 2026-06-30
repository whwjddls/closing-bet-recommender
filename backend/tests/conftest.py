import pytest


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
