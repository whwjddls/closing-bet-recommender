import numpy as np
import pandas as pd
import pytest

from app.backtest.ic import walk_forward_rank_ic, ICResult


def _two_date_panel():
    # date A: 신호 순위 = 선행수익률 순위 → spearman 1.0
    # date B: 신호[1,2,3] vs fwd[1,3,2] → spearman 0.5
    rows = [
        ("A", "t1", 1.0, 1.0), ("A", "t2", 2.0, 2.0), ("A", "t3", 3.0, 3.0),
        ("B", "t1", 1.0, 1.0), ("B", "t2", 2.0, 3.0), ("B", "t3", 3.0, 2.0),
    ]
    return pd.DataFrame(rows, columns=["date", "ticker", "signal", "fwd_ret"])


def test_walk_forward_rank_ic_mean_and_tstat():
    res = walk_forward_rank_ic(_two_date_panel(), "signal", "fwd_ret")
    assert isinstance(res, ICResult)
    assert res.n_periods == 2
    assert res.mean_ic == pytest.approx(0.75)
    # ic 시계열 [1.0, 0.5] → sd(ddof=1)=0.35355, t = 0.75/(0.35355/sqrt(2)) = 3.0
    assert res.t_stat == pytest.approx(3.0, abs=1e-6)


def test_walk_forward_skips_degenerate_dates():
    # 한 종목뿐인 날짜는 횡단면 상관 불가 → 제외
    df = pd.DataFrame(
        {"date": ["A"], "ticker": ["t1"], "signal": [1.0], "fwd_ret": [1.0]}
    )
    res = walk_forward_rank_ic(df, "signal", "fwd_ret")
    assert res.n_periods == 0
    assert np.isnan(res.mean_ic)
