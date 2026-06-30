# backend/tests/engine/test_pricing.py
import pytest

from app.engine.pricing import stop_price, target_price, freeze_prices


def test_stop_price_takes_tighter_of_atr_and_3pct():
    # buy-1.0*ATR=9800 vs buy*0.97=9700 → max=9800
    assert stop_price(10000, 200) == pytest.approx(9800)
    # buy-1.0*ATR=9000 vs buy*0.97=9700 → max=9700 (3% 바닥)
    assert stop_price(10000, 1000) == pytest.approx(9700)


def test_target_price_caps_at_prev_high_when_above():
    assert target_price(10000, 200, prev_high=10500) == pytest.approx(10240)  # min(10240,10500)
    assert target_price(10000, 200, prev_high=10100) == pytest.approx(10100)  # 전고점 캡


def test_target_price_no_cap_when_prev_high_below_buy():
    assert target_price(10000, 200, prev_high=9900) == pytest.approx(10240)


def test_freeze_prices_uses_provisional_buy_and_exit_cta():
    f = freeze_prices(p_now_provisional=10000, atr20=200, prev_high=10500)
    assert f.buy_price_provisional == 10000
    assert f.target_price == pytest.approx(10240)
    assert f.stop_price == pytest.approx(9800)
    assert "VWAP" in f.exit_cta


def test_freeze_prices_is_deterministic():
    a = freeze_prices(10000, 200, 10500)
    b = freeze_prices(10000, 200, 10500)
    assert a == b
