import pytest

from app.engine.signals.rvol import compute_rvol, s_geo, rvol_confirm


def test_compute_rvol_ratio():
    assert compute_rvol(2500, 1000) == pytest.approx(2.5)


def test_compute_rvol_unaccumulated_returns_none():
    assert compute_rvol(2500, None) is None
    assert compute_rvol(2500, 0) is None


@pytest.mark.parametrize(
    "rvol, expected",
    [(1.0, 0.0), (3.0, 1.0), (9.0, 1.0), (0.5, 0.0), (2.5, 0.834044)],
)
def test_s_geo_clip(rvol, expected):
    assert s_geo(rvol) == pytest.approx(expected, abs=1e-5)


def test_rvol_confirm_floor_and_full():
    assert rvol_confirm(1.0) == pytest.approx(0.6)   # 거래량 빈약 돌파 할인
    assert rvol_confirm(3.0) == pytest.approx(1.0)   # 충분 → 만점


def test_rvol_confirm_worked_example():
    assert rvol_confirm(2.5) == pytest.approx(0.933618, abs=1e-5)


def test_rvol_confirm_none_is_neutral():
    # 분모 미축적(~20세션 미만) → 중립 1.0 (거 축 가중-언락 보류)
    assert rvol_confirm(None) == pytest.approx(1.0)
