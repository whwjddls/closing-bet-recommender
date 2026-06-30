"""검증: walk-forward rank-IC · 신-직교화 incremental-IC · 베이스라인 · 수용기준."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ICResult:
    mean_ic: float
    t_stat: float
    n_periods: int
    per_date: pd.Series


def _spearman(a: pd.Series, b: pd.Series) -> float:
    """횡단면 rank-IC = 순위들의 Pearson 상관(Spearman)."""
    valid = a.notna() & b.notna()
    if valid.sum() < 2:
        return np.nan
    ra = a[valid].rank()
    rb = b[valid].rank()
    if ra.std(ddof=0) == 0 or rb.std(ddof=0) == 0:
        return np.nan
    return float(ra.corr(rb))


def walk_forward_rank_ic(panel: pd.DataFrame, signal_col: str,
                         fwd_ret_col: str, date_col: str = "date") -> ICResult:
    """날짜별 횡단면 rank-IC 시계열 → 평균·t통계량.
    t = mean / (sd/sqrt(n)). 워크포워드: 각 t 신호 vs t+1 선행수익률."""
    per_date = panel.groupby(date_col, sort=True).apply(
        lambda g: _spearman(g[signal_col], g[fwd_ret_col]), include_groups=False
    ).dropna()
    n = int(len(per_date))
    mean = float(per_date.mean()) if n else float("nan")
    if n > 1:
        sd = float(per_date.std(ddof=1))
        t_stat = mean / (sd / np.sqrt(n)) if sd > 0 else float("nan")
    else:
        t_stat = float("nan")
    return ICResult(mean_ic=mean, t_stat=t_stat, n_periods=n, per_date=per_date)


def orthogonalize(panel: pd.DataFrame, target_col: str, basis_cols: list,
                  date_col: str = "date") -> pd.Series:
    """각 날짜 횡단면에서 target 을 basis(=신 등)로 OLS 회귀한 잔차.
    거·수급의 incremental-IC 를 신과의 공유분산에 속지 않게 만든다(§7 직교화)."""
    def _resid(g: pd.DataFrame) -> pd.Series:
        y = g[target_col].astype(float)
        X = g[basis_cols].astype(float)
        valid = y.notna() & X.notna().all(axis=1)
        out = pd.Series(np.nan, index=g.index)
        k = len(basis_cols)
        if valid.sum() > k + 1:
            Xm = np.column_stack([np.ones(valid.sum()), X[valid].to_numpy()])
            yv = y[valid].to_numpy()
            beta, *_ = np.linalg.lstsq(Xm, yv, rcond=None)
            resid = yv - Xm @ beta
            # 완전 공선성 잔차는 수치적으로만 비0(~1e-15)이다. 정확히 0으로 스냅해
            # rank-IC 가 부동소수 잡음을 정보로 오인하지 않게 한다(§7 공유분산 제거).
            scale = max(float(np.max(np.abs(yv))), 1.0)
            resid[np.abs(resid) < 1e-9 * scale] = 0.0
            out.loc[valid] = resid
        return out

    return panel.groupby(date_col, sort=False, group_keys=False).apply(
        _resid, include_groups=False
    )


def incremental_ic(panel: pd.DataFrame, signal_col: str, basis_cols: list,
                   fwd_ret_col: str, date_col: str = "date") -> ICResult:
    """신에 직교화한 잔차의 walk-forward rank-IC = incremental-IC."""
    work = panel.copy()
    work["_resid"] = orthogonalize(panel, signal_col, basis_cols, date_col)
    return walk_forward_rank_ic(work, "_resid", fwd_ret_col, date_col)


class DartPointInTimeError(Exception):
    """DART 접수시각(≤15:20) 시점복원 불가 → veto 는 incremental-IC 회계에서 제외."""


@dataclass
class AcceptanceVerdict:
    verdict: str   # "GO" / "NO_GO" / "DOWNSCOPE"
    reason: str
    ic: float
    t_stat: float
    baseline_ic: float


def baseline_ic(panel: pd.DataFrame, fwd_ret_col: str, kind: str = "random",
                seed: int = 0, date_col: str = "date") -> ICResult:
    """베이스라인 IC. random=무작위 신호(종목선택 스킬 0 기준),
    overnight_etf=횡단면 무정보(상수) 신호."""
    work = panel.copy()
    if kind == "random":
        rng = np.random.default_rng(seed)
        work["_base"] = rng.standard_normal(len(work))
    elif kind == "overnight_etf":
        # 오버나잇-ETF: 종목 무차별 매수 → 횡단면 정보 없음(IC≈0 기준선)
        work["_base"] = 0.0
    else:
        raise ValueError(f"unknown baseline kind: {kind}")
    return walk_forward_rank_ic(work, "_base", fwd_ret_col, date_col)


def acceptance(ic: ICResult, baseline: ICResult, *,
               survivorship_source: bool) -> AcceptanceVerdict:
    """수용기준(§2.4): rank-IC>0, t>2, 베이스라인 상회 → GO.
    생존편향 소스 미확보 시 어떤 go/no-go 주장도 보류(DOWNSCOPE, §10.3)."""
    if not survivorship_source:
        return AcceptanceVerdict(
            "DOWNSCOPE",
            "생존편향 소스(상폐/정리매매 스냅샷) 미확보 — go/no-go 주장 보류(§10.3)",
            ic.mean_ic, ic.t_stat, baseline.mean_ic,
        )
    cond_t = (ic.t_stat is not None) and (not np.isnan(ic.t_stat)) and (ic.t_stat > 2.0)
    cond_pos = (not np.isnan(ic.mean_ic)) and (ic.mean_ic > 0)
    cond_base = np.isnan(baseline.mean_ic) or (ic.mean_ic > baseline.mean_ic)
    if cond_t and cond_pos and cond_base:
        return AcceptanceVerdict(
            "GO", "rank-IC>0 · t>2 · 베이스라인 상회(§2.4)",
            ic.mean_ic, ic.t_stat, baseline.mean_ic,
        )
    return AcceptanceVerdict(
        "NO_GO", "수용기준(t>2 & IC>0 & 베이스라인 상회) 미충족",
        ic.mean_ic, ic.t_stat, baseline.mean_ic,
    )


def assert_veto_backtestable(point_in_time_dart: bool) -> None:
    """DART 접수시각을 ≤15:20 으로 복원 가능할 때만 veto 를 incremental-IC 회계에 포함.
    불가하면 point-in-time-backtestable 아님 → 제외(DartPointInTimeError)."""
    if not point_in_time_dart:
        raise DartPointInTimeError(
            "DART list.json 일자粒度 — 접수시각 ≤15:20 복원 불가: "
            "veto 는 incremental-IC 회계에서 제외(룩어헤드 caveat, §7)"
        )
