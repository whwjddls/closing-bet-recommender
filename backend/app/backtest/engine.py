"""순수 pandas 백테스트 엔진: 확정 close[t] 진입 / 익일 오전 VWAP[t+1] 채점.
성공 = vwap_0900_1000[t+1] / close[t] − 1 > 0. VWAP 결측 → N/A(분모 제외)."""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from app.backtest.ic import walk_forward_rank_ic, baseline_ic, acceptance

SUCCESS = "SUCCESS"
FAIL = "FAIL"
NA = "NA"


def compute_outcomes(picks: pd.DataFrame) -> pd.DataFrame:
    """picks: [..., entry_price(=확정 close[t]), vwap_0900_1000(=t+1, 결측 가능)].
    morning_return 과 outcome(SUCCESS/FAIL/NA) 컬럼을 추가해 반환.
    N/A(진입가<=0 또는 VWAP 결측)는 morning_return 을 NaN 으로 둬 분모에서 제외."""
    out = picks.copy()
    entry = out["entry_price"].astype(float)
    vwap = out["vwap_0900_1000"].astype(float)
    is_na = vwap.isna() | entry.isna() | (entry <= 0)
    ret = vwap / entry.where(entry > 0) - 1.0

    outcome = np.where(is_na, NA, np.where(ret > 0, SUCCESS, FAIL))

    out["morning_return"] = ret
    out["outcome"] = outcome
    out.loc[is_na, "morning_return"] = np.nan
    return out


def next_trading_day(trading_days, d):
    """정렬된 거래일 목록에서 d 직후 거래일(t+1)을 반환. 없으면 NaT."""
    days = sorted(pd.to_datetime(list(trading_days)))
    d = pd.Timestamp(d)
    for x in days:
        if x > d:
            return x
    return pd.NaT


def attach_eval_dates(picks: pd.DataFrame, trading_days) -> pd.DataFrame:
    """각 run_date(t)의 채점일 eval_date = 다음 거래일(t+1)을 부착."""
    out = picks.copy()
    out["eval_date"] = [next_trading_day(trading_days, d) for d in out["run_date"]]
    return out


def attach_entry_close(picks: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    """진입가 = 확정 close[t]. panel[date==run_date] 의 close 를 결합."""
    cl = panel.rename(columns={"date": "run_date", "close": "entry_price"})
    cl = cl[["run_date", "ticker", "entry_price"]]
    return picks.merge(cl, on=["run_date", "ticker"], how="left")


def score(picks: pd.DataFrame, vwap_panel: pd.DataFrame) -> pd.DataFrame:
    """picks[run_date,eval_date,ticker,entry_price] 에 t+1 오전 VWAP 을 결합해 채점."""
    merged = picks.merge(
        vwap_panel[["eval_date", "ticker", "vwap_0900_1000"]],
        on=["eval_date", "ticker"], how="left",
    )
    return compute_outcomes(merged)


def summarize(scored: pd.DataFrame) -> dict:
    """집계: 적중률·평균 오전수익률(N/A 분모 제외)·N/A 건수."""
    graded = scored[scored["outcome"] != NA]
    n = int(len(graded))
    n_na = int((scored["outcome"] == NA).sum())
    hits = int((graded["outcome"] == SUCCESS).sum())
    return {
        "n": n,
        "n_na": n_na,
        "hit_rate": (hits / n) if n else float("nan"),
        "avg_morning_return": float(graded["morning_return"].mean()) if n else float("nan"),
    }


def run_cli(panel_path: str, *, signal_col: str, fwd_ret_col: str,
            survivorship_source: bool, date_col: str = "date") -> dict:
    """백테스트 CLI 코어: 시그널·선행수익률 패널 CSV → rank-IC·베이스라인·수용판정.
    생존편향 소스 미확보 시 acceptance 가 DOWNSCOPE 로 게이팅."""
    panel = pd.read_csv(panel_path, parse_dates=[date_col])
    ic = walk_forward_rank_ic(panel, signal_col, fwd_ret_col, date_col)
    base = baseline_ic(panel, fwd_ret_col, kind="random", seed=0, date_col=date_col)
    verdict = acceptance(ic, base, survivorship_source=survivorship_source)
    return {
        "ic": {"mean_ic": ic.mean_ic, "t_stat": ic.t_stat, "n_periods": ic.n_periods},
        "baseline_ic": base.mean_ic,
        "verdict": {
            "verdict": verdict.verdict, "reason": verdict.reason,
            "ic": verdict.ic, "t_stat": verdict.t_stat,
            "baseline_ic": verdict.baseline_ic,
        },
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="종가베팅 백테스트 검증 CLI")
    parser.add_argument("panel_path", help="signal·fwd_ret 결합 패널 CSV 경로")
    parser.add_argument("--signal-col", default="signal")
    parser.add_argument("--fwd-ret-col", default="fwd_ret")
    parser.add_argument("--date-col", default="date")
    parser.add_argument("--survivorship-source", action="store_true",
                        help="상폐/정리매매 스냅샷 확보 여부(미지정 시 DOWNSCOPE 게이팅)")
    args = parser.parse_args(argv)
    result = run_cli(
        args.panel_path, signal_col=args.signal_col, fwd_ret_col=args.fwd_ret_col,
        survivorship_source=args.survivorship_source, date_col=args.date_col,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
