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


def point_in_time_universe(membership, as_of_date) -> set:
    """as_of(t) 시점의 상장 종목 집합. listing_date <= t < delisting_date.
    이후 상폐된 종목도 t 시점엔 포함 → 생존편향 제거.
    membership: DataFrame[ticker, listing_date, delisting_date(NaT 가능)].
    소스가 없으면 '오늘 목록'으로 조용히 폴백하지 않고 fail-closed(SurvivorshipSourceMissing)."""
    if membership is None or len(membership) == 0:
        raise SurvivorshipSourceMissing(
            "point-in-time 유니버스 소스(상폐/정리매매 versioned 스냅샷) 미확보 "
            "— 생존편향 게이팅: go/no-go 주장 보류(§10.3)"
        )
    d = pd.Timestamp(as_of_date)
    listing = pd.to_datetime(membership["listing_date"])
    delisting = pd.to_datetime(membership["delisting_date"])
    is_listed = listing <= d
    not_delisted = delisting.isna() | (delisting > d)
    return set(membership.loc[is_listed & not_delisted, "ticker"])


def reconstruct_pool(value_panel: pd.DataFrame, as_of_date, universe: set,
                     top_n: int = 200) -> list:
    """D-1(직전 거래일) 거래대금 상위 top_n 후보 풀을 시점기준으로 재현.
    결정성: value 내림차순, 동점은 ticker 오름차순(mergesort 안정정렬).
    당일/미래 행은 guard_final_dates 로 차단."""
    d = pd.Timestamp(as_of_date)
    dates = pd.to_datetime(value_panel["date"])
    hist = value_panel[dates < d]
    if hist.empty:
        return []
    d1 = pd.to_datetime(hist["date"]).max()  # 직전 거래일
    guard_final_dates(as_of_date, [d1], label="pool D-1")
    snap = hist[pd.to_datetime(hist["date"]) == d1]
    snap = snap[snap["ticker"].isin(universe)]
    snap = snap.sort_values(
        ["value", "ticker"], ascending=[False, True], kind="mergesort"
    )
    return snap["ticker"].head(top_n).tolist()


def live_top30_only_rate(live_picks, d1_pool) -> float:
    """라이브 top-30 단독발생 비율 = D-1 재현 풀에 없는 픽 / 전체 픽.
    이 성분은 백테스트에 부재하므로 §7 수용기준에서 분리, paper-forward 검증 대상."""
    if not live_picks:
        return 0.0
    d1 = set(d1_pool)
    only = sum(1 for t in live_picks if t not in d1)
    return only / len(live_picks)


def build_pnow_proxy(close_t: float, haircut: float = 0.0,
                     band: float = 0.0) -> dict:
    """인트라데이 15:20 이력이 없는 구간의 P_now 프록시.
    central = close[t]·(1−haircut)  (측정된 EOD→15:20 드리프트 평균),
    low/high = central·(1∓band)     (민감도 밴드 — 각주 아닌 정량 밴드).
    haircut=band=0 이면 프록시 = close[t]."""
    central = close_t * (1.0 - haircut)
    return {
        "central": central,
        "low": central * (1.0 - band),
        "high": central * (1.0 + band),
    }
