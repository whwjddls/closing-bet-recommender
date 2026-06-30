import pytest

from app.engine.signals.regime import classify_regime, compute_regime


@pytest.mark.parametrize(
    "cond_a, cond_b, expected",
    [
        (True, True, 1.0),    # 상승 5MA 위
        (True, False, 0.5),   # 5MA 위·꺾임(약화)
        (False, True, 0.5),   # 상승 5MA 아래(눌림)
        (False, False, 0.0),  # 하락추세 → 중단
    ],
)
def test_classify_regime_truth_table_exhaustive(cond_a, cond_b, expected):
    assert classify_regime(cond_a, cond_b) == expected


def test_compute_regime_up_up():
    # ma5=(100+99+98+97+96)/5=98, ma5_prev=(99+98+97+96+95)/5=97
    r = compute_regime(index_level=100.0, prev5_closes=[99, 98, 97, 96, 95])
    assert r.cond_a is True and r.cond_b is True
    assert r.ma5 == pytest.approx(98.0) and r.ma5_prev == pytest.approx(97.0)
    assert r.regime_mult == 1.0


def test_compute_regime_off_off():
    r = compute_regime(index_level=90.0, prev5_closes=[95, 96, 97, 98, 99])
    assert r.cond_a is False and r.cond_b is False
    assert r.regime_mult == 0.0


def test_compute_regime_requires_five_closes():
    with pytest.raises(ValueError):
        compute_regime(100.0, [99, 98, 97, 96])
