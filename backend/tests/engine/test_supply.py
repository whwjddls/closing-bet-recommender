import pytest

from app.engine.signals.supply import supply_z, supply_tilt


def test_supply_z_worked_example():
    assert supply_z(80, 500) == pytest.approx(0.16)


def test_supply_z_clips_both_directions():
    assert supply_z(900, 500) == 1.0     # 순매수 과다 → 상한 클립
    assert supply_z(-900, 500) == -1.0   # 순매도 과다 → 하한 클립


def test_supply_z_zero_denominator_guard():
    assert supply_z(80, 0) == 0.0


def test_supply_tilt_bidirectional():
    assert supply_tilt(0.16) == pytest.approx(1.032)   # 순매수 부스트
    assert supply_tilt(0.0) == pytest.approx(1.0)
    assert supply_tilt(-1.0) == pytest.approx(0.8)     # 순매도 패널티(하한)
    assert supply_tilt(1.0) == pytest.approx(1.2)      # 상한
