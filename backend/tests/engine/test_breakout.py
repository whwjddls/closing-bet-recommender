import pytest

from app.engine.signals.breakout import term, s_shin


@pytest.mark.parametrize(
    "near, expected",
    [
        (0.90, 0.0),    # 근접 base 시작점
        (0.95, 0.5),    # base 중간
        (1.00, 1.0),    # 전고점 도달, 마그니튜드 0
        (1.05, 1.3),    # 마그니튜드 캡: 1.0 + 0.3
        (1.10, 1.3),    # 캡 유지
        (0.80, 0.0),    # base 하한 클립
    ],
)
def test_term_boundaries_and_magnitude_cap(near, expected):
    assert term(near) == pytest.approx(expected)


def test_s_shin_full_history_worked_example():
    # KOSDAQ A: P_now=24500, H252=24000, H60=23500
    r = s_shin(p_now=24500, high_60=23500, high_252=24000, listing_days=252)
    assert r.near_252 == pytest.approx(1.020833, abs=1e-5)
    assert r.near_60 == pytest.approx(1.042553, abs=1e-5)
    assert r.s_shin == pytest.approx(1.164096, abs=1e-4)
    assert r.label == "52주 신고가"


def test_s_shin_boundary_251_uses_near60_only():
    r = s_shin(p_now=24500, high_60=23500, high_252=24000, listing_days=251)
    assert r.near_252 is None
    assert r.s_shin == pytest.approx(term(24500 / 23500), abs=1e-9)  # 가중 1.0 재정규화
    assert r.label == "가용구간 고가"


def test_s_shin_boundary_252_uses_full():
    r = s_shin(p_now=24500, high_60=23500, high_252=24000, listing_days=252)
    assert r.near_252 is not None


def test_s_shin_no_252_history_renormalizes_to_near60():
    r = s_shin(p_now=24500, high_60=23500, high_252=None, listing_days=200)
    assert r.near_252 is None
    assert r.s_shin == pytest.approx(term(24500 / 23500), abs=1e-9)


def test_s_shin_excludes_under_120_listing_days():
    with pytest.raises(ValueError):
        s_shin(p_now=24500, high_60=23500, high_252=None, listing_days=119)
