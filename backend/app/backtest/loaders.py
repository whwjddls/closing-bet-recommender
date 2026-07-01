"""프로덕션 백테스트 패널 로더 (pykrx 기반) — 04 `/backtest` 기본 러너가 바인딩한다.

- ``load_price_panel`` → ``[date, ticker, close, signal]``: 확정 종가 진입가 + 신고가
  근접(H_ref 당일 제외) 신호.
- ``load_vwap_panel`` → ``[eval_date, ticker, vwap_0900_1000]``: 익일 오전 진입 프록시.

pykrx 는 일봉만 제공하므로 09:00–10:00 분봉 VWAP 의 역사적 재현은 불가하다 →
익일 시가(open)를 오전 진입 프록시로 사용한다(문서화된 근사; 실 분봉 VWAP 은 KIS 라이브
전용). 룩어헤드 금지: 신호의 H_ref 는 당일을 제외한다(rolling_high_excluding_current).
외부 pykrx 모듈은 지연 로드(_load_pykrx)라 테스트는 그 seam 만 대체하면 된다.
"""
from __future__ import annotations

import datetime as dt

import pandas as pd

import app.data.pykrx_client as pykrx_client
from app.backtest.reconstruct import rolling_high_excluding_current

WINDOW_252 = 252            # 52주 신고가 근접 신호 윈도우(거래일)
LOOKBACK_DAYS = 400         # ≥252 거래일 확보용 달력 룩백
EVAL_BUFFER_DAYS = 5        # 익일(eval) 시가 확보용 종료일 버퍼(주말 흡수)


def _yyyymmdd(d: dt.date) -> str:
    return d.strftime("%Y%m%d")


def _resolve_pykrx(pykrx_module):
    return pykrx_module if pykrx_module is not None else pykrx_client._load_pykrx()


def _universe(px, as_of: dt.date) -> list[str]:
    return [str(t) for t in px.get_market_ticker_list(_yyyymmdd(as_of), "ALL")]


def load_price_panel(start: dt.date, end: dt.date, pykrx_module=None) -> pd.DataFrame:
    """[date, ticker, close, signal] — end 시점 유니버스의 [start,end] 확정 일봉.
    signal = close / H_ref_252(당일 제외) 신고가 근접도(룩어헤드 금지)."""
    px = _resolve_pykrx(pykrx_module)
    frm = _yyyymmdd(start - dt.timedelta(days=LOOKBACK_DAYS))
    to = _yyyymmdd(end)
    rows: list[dict] = []
    for ticker in _universe(px, end):
        df = px.get_market_ohlcv(frm, to, ticker)
        if df is None or len(df) == 0:
            continue
        close = df[pykrx_client.COL_CLOSE].astype(float)
        high = df[pykrx_client.COL_HIGH].astype(float)
        href = rolling_high_excluding_current(high, WINDOW_252)   # 당일 제외 52주 고가
        signal = close / href
        for idx in df.index:
            d = pykrx_client._parse_day(idx)
            if d is None or not (start <= d <= end):
                continue
            sig = signal.loc[idx]
            rows.append({
                "date": pd.Timestamp(d),
                "ticker": ticker,
                "close": float(close.loc[idx]),
                "signal": float(sig) if pd.notna(sig) else float("nan"),
            })
    return pd.DataFrame(rows, columns=["date", "ticker", "close", "signal"])


def load_vwap_panel(start: dt.date, end: dt.date, pykrx_module=None) -> pd.DataFrame:
    """[eval_date, ticker, vwap_0900_1000] — 익일 오전 진입 프록시(익일 시가).
    eval_date 는 start 다음 거래일부터(각 run_date t 의 t+1 채점일)."""
    px = _resolve_pykrx(pykrx_module)
    frm = _yyyymmdd(start)
    to = _yyyymmdd(end + dt.timedelta(days=EVAL_BUFFER_DAYS))      # 익일 시가 확보 버퍼
    rows: list[dict] = []
    for ticker in _universe(px, end):
        df = px.get_market_ohlcv(frm, to, ticker)
        if df is None or len(df) == 0:
            continue
        opens = df[pykrx_client.COL_OPEN].astype(float)
        for idx in df.index:
            d = pykrx_client._parse_day(idx)
            if d is None or d <= start:                           # eval_date > run_date(≥start)
                continue
            rows.append({
                "eval_date": pd.Timestamp(d),
                "ticker": ticker,
                "vwap_0900_1000": float(opens.loc[idx]),
            })
    return pd.DataFrame(rows, columns=["eval_date", "ticker", "vwap_0900_1000"])
