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
import logging
import threading

import pandas as pd

import app.data.pykrx_client as pykrx_client
from app.backtest.reconstruct import rolling_high_excluding_current

logger = logging.getLogger(__name__)

WINDOW_252 = 252            # 52주 신고가 근접 신호 윈도우(거래일)
LOOKBACK_DAYS = 400         # ≥252 거래일 확보용 달력 룩백
EVAL_BUFFER_DAYS = 5        # 익일(eval) 시가 확보용 종료일 버퍼(주말 흡수)
# 실측(2026-07-03): 전종목(2800+) 순회 중 pykrx가 특정 티커에서 응답 없이
# 무한 대기할 수 있다(라이브 파이프라인은 try/except로 방어되지만 여긴 hang이라
# except로도 못 잡음). 별도 스레드+join(timeout)으로 강제 스킵한다.
OHLCV_TIMEOUT_SEC = 15.0
PROGRESS_EVERY = 200        # N종목마다 진행상황 로그(장시간 배치 가시성)


def _fetch_ohlcv_safe(px, frm: str, to: str, ticker: str,
                      timeout_sec: float = OHLCV_TIMEOUT_SEC):
    """px.get_market_ohlcv 를 타임아웃으로 보호. 무응답(hang)/예외 시 None(스킵).

    daemon 스레드에 위임 후 join(timeout)만 한다 — 스레드 자체는 강제 종료할 수
    없으므로 타임아웃된 호출은 백그라운드에 남아있다 스스로 끝나거나 프로세스
    종료 시 함께 사라진다(데몬). 메인 루프는 기다리지 않고 다음 티커로 진행."""
    result: dict = {}

    def _call():
        try:
            result["df"] = px.get_market_ohlcv(frm, to, ticker)
        except Exception as exc:                          # noqa: BLE001  (외부 IO)
            result["error"] = exc

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=timeout_sec)
    if t.is_alive():
        logger.warning("ohlcv 무응답(%.0fs 초과) — 스킵: %s", timeout_sec, ticker)
        return None
    if "error" in result:
        logger.warning("ohlcv 조회 실패 — 스킵: %s (%s)", ticker, result["error"])
        return None
    return result.get("df")


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
    universe = _universe(px, end)
    rows: list[dict] = []
    for i, ticker in enumerate(universe):
        if i and i % PROGRESS_EVERY == 0:
            logger.info("load_price_panel 진행: %d/%d", i, len(universe))
        df = _fetch_ohlcv_safe(px, frm, to, ticker, timeout_sec=OHLCV_TIMEOUT_SEC)
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
    universe = _universe(px, end)
    rows: list[dict] = []
    for i, ticker in enumerate(universe):
        if i and i % PROGRESS_EVERY == 0:
            logger.info("load_vwap_panel 진행: %d/%d", i, len(universe))
        df = _fetch_ohlcv_safe(px, frm, to, ticker, timeout_sec=OHLCV_TIMEOUT_SEC)
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
