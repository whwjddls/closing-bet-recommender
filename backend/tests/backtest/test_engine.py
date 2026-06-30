import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import compute_outcomes, SUCCESS, FAIL, NA


def test_compute_outcomes_success_fail_na():
    picks = pd.DataFrame(
        {
            "ticker": ["A", "B", "C", "D"],
            "entry_price": [100.0, 100.0, 100.0, 0.0],   # D: 비정상 진입가
            "vwap_0900_1000": [101.0, 99.0, np.nan, 50.0],  # C: 오전 VWAP 결측/잠김
        }
    )
    out = compute_outcomes(picks)
    res = dict(zip(out["ticker"], out["outcome"]))
    assert res["A"] == SUCCESS           # 101/100-1 = +1% > 0
    assert res["B"] == FAIL              # 99/100-1 < 0
    assert res["C"] == NA                # VWAP 결측 → N/A
    assert res["D"] == NA                # 진입가 <=0 → N/A
    # 성공 종목의 morning_return
    assert out.loc[out.ticker == "A", "morning_return"].iloc[0] == \
        pytest.approx(0.01)
    # N/A 행의 morning_return 은 NaN (0점 처리 금지, 분모 제외 대상)
    assert out.loc[out.ticker == "C", "morning_return"].isna().all()


def test_compute_outcomes_exact_break_even_is_fail():
    # 정확히 0% 는 '> 0' 아님 → 실패(성공 정의 엄격 부등호)
    picks = pd.DataFrame(
        {"ticker": ["E"], "entry_price": [100.0], "vwap_0900_1000": [100.0]}
    )
    assert compute_outcomes(picks)["outcome"].iloc[0] == FAIL
