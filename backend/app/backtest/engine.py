"""순수 pandas 백테스트 엔진: 확정 close[t] 진입 / 익일 오전 VWAP[t+1] 채점.
성공 = vwap_0900_1000[t+1] / close[t] − 1 > 0. VWAP 결측 → N/A(분모 제외)."""
from __future__ import annotations

import numpy as np
import pandas as pd

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
