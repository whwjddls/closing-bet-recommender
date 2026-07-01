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


from app.backtest.engine import (
    next_trading_day,
    attach_eval_dates,
    attach_entry_close,
    score,
    summarize,
)


def test_next_trading_day_skips_to_following_session():
    days = ["2026-06-29", "2026-06-30", "2026-07-01"]
    assert next_trading_day(days, "2026-06-30") == pd.Timestamp("2026-07-01")
    assert pd.isna(next_trading_day(days, "2026-07-01"))  # 다음 거래일 없음


def test_score_and_summarize_excludes_na_from_denominator():
    panel = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-06-30", "2026-06-30"]),
            "ticker": ["A", "B"],
            "close": [100.0, 200.0],
        }
    )
    picks = pd.DataFrame(
        {"run_date": pd.to_datetime(["2026-06-30", "2026-06-30"]),
         "ticker": ["A", "B"]}
    )
    vwap_panel = pd.DataFrame(
        {
            "eval_date": pd.to_datetime(["2026-07-01", "2026-07-01"]),
            "ticker": ["A", "B"],
            "vwap_0900_1000": [101.0, np.nan],  # B 는 오전 잠김 → N/A
        }
    )
    trading_days = ["2026-06-30", "2026-07-01"]

    picks2 = attach_eval_dates(picks, trading_days)
    picks2 = attach_entry_close(picks2, panel)
    scored = score(picks2, vwap_panel)
    s = summarize(scored)

    assert s["n"] == 1          # A 만 분모(B 는 N/A 제외)
    assert s["n_na"] == 1
    assert s["hit_rate"] == pytest.approx(1.0)   # A 성공 1/1
    assert s["avg_morning_return"] == pytest.approx(0.01)


from datetime import date

from app.backtest.engine import run_backtest, BacktestResult


def test_run_backtest_composes_reconstruct_score_summarize_ic_end_to_end():
    # 외부 API(KIS/pykrx) 직접 호출 없이 주입 콜러블로 전체 합성을 검증.
    # 신호 A>B>C, 익일 오전 VWAP(09:00–10:00)으로 t→t+1 채점.
    def load_price_panel(start, end):
        return pd.DataFrame(
            {
                "date": pd.to_datetime(
                    ["2026-06-29", "2026-06-29", "2026-06-29",
                     "2026-06-30", "2026-06-30", "2026-06-30"]
                ),
                "ticker": ["A", "B", "C", "A", "B", "C"],
                "close": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
                "signal": [3.0, 2.0, 1.0, 3.0, 2.0, 1.0],
            }
        )

    def load_vwap_panel(start, end):
        # eval_date = run_date(t)의 다음 거래일(t+1). 오전 09:00–10:00 VWAP.
        return pd.DataFrame(
            {
                "eval_date": pd.to_datetime(
                    ["2026-06-30", "2026-06-30", "2026-06-30",
                     "2026-07-01", "2026-07-01", "2026-07-01"]
                ),
                "ticker": ["A", "B", "C", "A", "B", "C"],
                # date1: 수익률 순위 = 신호 순위 → rank-IC 1.0
                # date2: B/C 뒤집힘 → rank-IC 0.5  (평균 0.75, t=3.0)
                "vwap_0900_1000": [103.0, 102.0, 101.0, 103.0, 101.0, 102.0],
            }
        )

    trading_days = ["2026-06-29", "2026-06-30", "2026-07-01"]

    res = run_backtest(
        date(2026, 6, 29),
        date(2026, 6, 30),
        load_price_panel=load_price_panel,
        load_vwap_panel=load_vwap_panel,
        trading_days=trading_days,
        survivorship_source=True,
    )

    assert isinstance(res, BacktestResult)
    assert res.start == date(2026, 6, 29)
    assert res.end == date(2026, 6, 30)
    assert res.n_picks == 6                     # 6 픽 전부 t+1 VWAP 존재 → 채점(N·A 0)
    assert res.rank_ic == pytest.approx(0.75)   # per-date rank-IC [1.0, 0.5] 평균
    assert res.t_stat == pytest.approx(3.0)     # 0.75 / (0.35355/sqrt(2))
    assert res.hit_rate == pytest.approx(1.0)   # 전부 VWAP>close → 성공
    assert res.avg_return == pytest.approx(0.02)
    assert isinstance(res.note, str) and res.note  # 수용판정 사유 채워짐


def test_run_backtest_requires_injected_data_loaders():
    # (start,end)만으로는 외부 데이터 의존 — 주입 콜러블 없으면 fail-fast
    with pytest.raises(ValueError):
        run_backtest(date(2026, 6, 29), date(2026, 6, 30))


def _price_panel_abc(start, end):
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2026-06-29", "2026-06-29", "2026-06-29",
                 "2026-06-30", "2026-06-30", "2026-06-30"]
            ),
            "ticker": ["A", "B", "C", "A", "B", "C"],
            "close": [100.0] * 6,
            "signal": [3.0, 2.0, 1.0, 3.0, 2.0, 1.0],
        }
    )


def _vwap_panel_abc(start, end):
    return pd.DataFrame(
        {
            "eval_date": pd.to_datetime(
                ["2026-06-30", "2026-06-30", "2026-06-30",
                 "2026-07-01", "2026-07-01", "2026-07-01"]
            ),
            "ticker": ["A", "B", "C", "A", "B", "C"],
            "vwap_0900_1000": [103.0, 102.0, 101.0, 103.0, 102.0, 101.0],
        }
    )


_DAYS_ABC = ["2026-06-29", "2026-06-30", "2026-07-01"]


def test_run_backtest_does_not_silently_assume_survivorship_source():
    # survivorship_source 미지정 + membership 미확보 → 자동 True 금지.
    # acceptance 는 생존편향 게이팅으로 DOWNSCOPE(go/no-go 조용한 통과 방지, §10.3).
    res = run_backtest(
        date(2026, 6, 29), date(2026, 6, 30),
        load_price_panel=_price_panel_abc, load_vwap_panel=_vwap_panel_abc,
        trading_days=_DAYS_ABC,
    )
    assert "DOWNSCOPE" in res.note


def test_run_backtest_restricts_to_point_in_time_universe_with_membership():
    # membership 소스가 있으면 각 run_date 시점 상장종목으로 픽을 제한(생존편향 제거)하고
    # n_picks 를 그 재구성 기준으로 센다. C 는 membership 밖 → 제외 → A,B × 2일 = 4픽.
    membership = pd.DataFrame(
        {
            "ticker": ["A", "B"],
            "listing_date": ["2000-01-01", "2000-01-01"],
            "delisting_date": [pd.NaT, pd.NaT],
        }
    )
    res = run_backtest(
        date(2026, 6, 29), date(2026, 6, 30),
        load_price_panel=_price_panel_abc, load_vwap_panel=_vwap_panel_abc,
        trading_days=_DAYS_ABC, membership=membership,
    )
    assert res.n_picks == 4
    assert "DOWNSCOPE" not in res.note        # membership 확보 → survivorship 파생 True
