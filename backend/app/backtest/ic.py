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
