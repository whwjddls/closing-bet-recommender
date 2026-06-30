# backend/tests/engine/test_scoring.py
import pytest

from app.engine.scoring import core_score, final_score


def test_core_is_product_of_three_axes():
    assert core_score(1.164096, 0.933618, 1.032) == pytest.approx(1.1217, abs=1e-3)


def test_worked_example_kosdaq_a_core():
    # s_신=1.164096, rvol_confirm=0.933618, supply_tilt=1.032 → core≈1.122 (등급 S)
    core = core_score(1.164096, 0.933618, 1.032)
    assert core == pytest.approx(1.122, abs=1e-3)


def test_final_applies_regime_and_veto_gating():
    core = 1.122
    assert final_score(core, 1.0, 1) == pytest.approx(1.122, abs=1e-3)
    assert final_score(core, 0.5, 1) == pytest.approx(0.561, abs=1e-3)
    assert final_score(core, 0.0, 1) == 0.0   # 하락 레짐 → 중단
    assert final_score(core, 1.0, 0) == 0.0   # veto → 차단
