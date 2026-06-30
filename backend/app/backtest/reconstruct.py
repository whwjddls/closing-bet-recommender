"""백테스트 시점복원(reconstruct): 룩어헤드 가드·point-in-time 유니버스·풀 재현·
15:20-등가 EOD 프록시·분할불변 거래대금·시그널 패널 DI seam."""
from __future__ import annotations

import pandas as pd


class LookaheadError(Exception):
    """FINAL/prefetch 경로에 당일(t) 또는 미래 데이터가 유입될 때."""


class SurvivorshipSourceMissing(Exception):
    """상폐/정리매매 versioned 스냅샷 미확보 — go/no-go 주장 게이팅."""


def guard_final_dates(as_of_date, dates, label: str = "FINAL") -> None:
    """FINAL 입력의 모든 날짜는 as_of(t)보다 '엄격히 이전'이어야 한다.
    t-당일 또는 미래 날짜가 하나라도 있으면 LookaheadError."""
    as_of = pd.Timestamp(as_of_date)
    bad = sorted({d for d in pd.to_datetime(list(dates)) if d >= as_of})
    if bad:
        sample = ", ".join(str(d.date()) for d in bad[:3])
        raise LookaheadError(
            f"{label} 입력에 당일/미래 데이터 유입(룩어헤드): as_of={as_of.date()}, 위반={sample}"
        )


def rolling_high_excluding_current(high: pd.Series, window: int) -> pd.Series:
    """H_ref = max(High[t-window .. t-1]). 당일 high[t]를 shift(1)로 제외해
    52주 신고가 근접도 계산의 룩어헤드를 원천 차단한다."""
    return high.shift(1).rolling(window=window, min_periods=1).max()
