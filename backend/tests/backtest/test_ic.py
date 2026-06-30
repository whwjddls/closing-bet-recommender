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


from app.backtest.ic import orthogonalize, incremental_ic


def _collinear_panel():
    # s_geo = 3 * s_shin (완전 선형종속). fwd_ret 은 s_shin 과 단조.
    rows = []
    for date in ["A", "B"]:
        for i, shin in enumerate([1.0, 2.0, 3.0, 4.0, 5.0], start=1):
            rows.append((date, f"t{i}", shin, 3.0 * shin, float(i)))
    return pd.DataFrame(rows, columns=["date", "ticker", "s_shin", "s_geo", "fwd_ret"])


def test_orthogonalize_residual_of_collinear_signal_is_zero():
    panel = _collinear_panel()
    resid = orthogonalize(panel, "s_geo", ["s_shin"])
    # s_geo 가 s_shin 의 정확한 선형함수 → 잔차 ≈ 0
    assert np.allclose(resid.values, 0.0, atol=1e-8)


def test_incremental_ic_removes_shared_variance_with_shin():
    panel = _collinear_panel()
    # 직교화 전 거(s_geo)의 naive IC 는 신과 같은 정보로 높게 나오지만,
    raw = walk_forward_rank_ic(panel, "s_geo", "fwd_ret")
    assert raw.mean_ic == pytest.approx(1.0)
    # 신에 직교화한 잔차의 incremental-IC 는 정보가 남지 않아 정의 불가(NaN)
    inc = incremental_ic(panel, "s_geo", ["s_shin"], "fwd_ret")
    assert np.isnan(inc.mean_ic)


from app.backtest.ic import (
    baseline_ic,
    acceptance,
    AcceptanceVerdict,
    assert_veto_backtestable,
    DartPointInTimeError,
)


def _ic(mean, t, n=10):
    return ICResult(mean_ic=mean, t_stat=t, n_periods=n,
                    per_date=pd.Series([mean] * n))


def test_baseline_random_is_near_zero():
    panel = _two_date_panel()
    base = baseline_ic(panel, "fwd_ret", kind="random", seed=0)
    assert abs(base.mean_ic) < 1.0  # 무작위 신호 → 약한 IC


def test_acceptance_go_when_t_gt2_positive_and_beats_baseline():
    v = acceptance(_ic(0.05, 3.0), _ic(0.0, 0.1), survivorship_source=True)
    assert isinstance(v, AcceptanceVerdict)
    assert v.verdict == "GO"


def test_acceptance_no_go_when_t_not_above_2():
    v = acceptance(_ic(0.05, 1.5), _ic(0.0, 0.1), survivorship_source=True)
    assert v.verdict == "NO_GO"


def test_acceptance_no_go_when_not_beating_baseline():
    v = acceptance(_ic(0.05, 3.0), _ic(0.06, 3.0), survivorship_source=True)
    assert v.verdict == "NO_GO"


def test_acceptance_downscope_when_survivorship_source_missing():
    # 상폐/정리매매 스냅샷 미확보 → go/no-go 주장 보류(DOWNSCOPE)
    v = acceptance(_ic(0.05, 3.0), _ic(0.0, 0.1), survivorship_source=False)
    assert v.verdict == "DOWNSCOPE"


def test_veto_excluded_from_ic_when_dart_timestamp_unavailable():
    # DART list.json 은 일자粒度 → 접수시각 복원 불가 시 veto 를 incremental-IC 회계에서 제외
    assert_veto_backtestable(point_in_time_dart=True)  # 통과(예외 없음)
    with pytest.raises(DartPointInTimeError):
        assert_veto_backtestable(point_in_time_dart=False)
