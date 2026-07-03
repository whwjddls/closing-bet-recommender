"""백테스트 로더의 pykrx 무응답(hang) 방어 — 실측(2026-07-03): 종목 1개가 무응답이면
로더 전체가 영원히 멈춤(라이브 파이프라인은 이미 try/except로 방어되지만 로더는 미방어였음)."""
import datetime as dt
import time

import numpy as np
import pandas as pd
import pytest

from app.backtest import loaders


def _fake_df(rows: int = 3) -> pd.DataFrame:
    idx = pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03"][:rows])
    return pd.DataFrame(
        {"시가": [100.0] * rows, "고가": [105.0] * rows, "저가": [99.0] * rows,
         "종가": [104.0] * rows, "거래량": [1000] * rows},
        index=idx,
    )


class _SlowPykrx:
    """지정 티커에서 timeout_sec 보다 오래 블로킹(무응답 재현)."""

    def __init__(self, hang_ticker: str, hang_seconds: float):
        self.hang_ticker = hang_ticker
        self.hang_seconds = hang_seconds
        self.calls: list[str] = []

    def get_market_ohlcv(self, frm, to, ticker):
        self.calls.append(ticker)
        if ticker == self.hang_ticker:
            time.sleep(self.hang_seconds)
        return _fake_df()


class _BoomPykrx:
    def get_market_ohlcv(self, frm, to, ticker):
        raise ConnectionError("KRX outage")


def test_fetch_ohlcv_safe_returns_result_when_fast():
    px = _SlowPykrx(hang_ticker="999999", hang_seconds=0)
    df = loaders._fetch_ohlcv_safe(px, "20260601", "20260603", "000660", timeout_sec=0.2)
    assert df is not None and len(df) == 3


def test_fetch_ohlcv_safe_skips_on_timeout_without_blocking():
    px = _SlowPykrx(hang_ticker="000660", hang_seconds=2.0)
    t0 = time.monotonic()
    df = loaders._fetch_ohlcv_safe(px, "20260601", "20260603", "000660", timeout_sec=0.2)
    elapsed = time.monotonic() - t0
    assert df is None                     # 무응답 → 스킵(크래시/영구대기 아님)
    assert elapsed < 1.0                  # 실제 hang(2초)만큼 기다리지 않음


def test_fetch_ohlcv_safe_skips_on_exception():
    df = loaders._fetch_ohlcv_safe(_BoomPykrx(), "20260601", "20260603", "000660", timeout_sec=0.2)
    assert df is None


def test_load_price_panel_skips_hanging_ticker_and_keeps_others(monkeypatch):
    # 유니버스 2종목 중 하나가 무응답이어도 전체가 멈추지 않고 나머지로 계속 진행.
    px = _SlowPykrx(hang_ticker="000001", hang_seconds=5.0)
    monkeypatch.setattr(loaders, "_universe", lambda _px, _asof: ["000001", "000660"])
    monkeypatch.setattr(loaders, "OHLCV_TIMEOUT_SEC", 0.2)

    import datetime as dt
    t0 = time.monotonic()
    panel = loaders.load_price_panel(dt.date(2026, 6, 1), dt.date(2026, 6, 3), pykrx_module=px)
    elapsed = time.monotonic() - t0

    assert elapsed < 2.0                                  # 5초 hang을 기다리지 않았음
    assert set(panel["ticker"].unique()) == {"000660"}    # 무응답 종목만 빠지고 나머지는 포함


class _ZeroRowPykrx:
    """거래정지 구간(0원 행) 포함 가짜 pykrx — 실측(2026-07-03): pykrx는 정지일을
    시/고/저/종가 전부 0인 행으로 반환한다. 0 종가는 signal=∞·fwd_ret=−100% 오염원."""

    def get_market_ohlcv(self, frm, to, ticker):
        idx = pd.to_datetime(["2026-06-01", "2026-06-02", "2026-06-03"])
        return pd.DataFrame(
            {"시가": [100.0, 0.0, 104.0], "고가": [105.0, 0.0, 110.0],
             "저가": [99.0, 0.0, 103.0], "종가": [104.0, 0.0, 109.0],
             "거래량": [1000, 0, 2000]},
            index=idx,
        )


def test_load_price_panel_drops_zero_close_rows(monkeypatch):
    # 0원 행이 rank-IC를 오염(신호 최하위·수익률 ∞ → 가짜 음의 상관)시키지 않도록 제외.
    monkeypatch.setattr(loaders, "_universe", lambda _px, _asof: ["000660"])
    panel = loaders.load_price_panel(
        dt.date(2026, 6, 1), dt.date(2026, 6, 3), pykrx_module=_ZeroRowPykrx())
    assert len(panel) == 2                                # 0원 행(6/2)만 제거
    assert (panel["close"] > 0).all()
    finite_signals = panel["signal"].dropna()
    assert np.isfinite(finite_signals).all()              # ∞ 신호 미유입


def test_load_vwap_panel_drops_zero_open_rows(monkeypatch):
    # 시가 0(정지일)은 익일 진입 프록시로 쓸 수 없음 — ret=−100% 가짜 수익률 방지.
    monkeypatch.setattr(loaders, "_universe", lambda _px, _asof: ["000660"])
    panel = loaders.load_vwap_panel(
        dt.date(2026, 6, 1), dt.date(2026, 6, 3), pykrx_module=_ZeroRowPykrx())
    assert (panel["vwap_0900_1000"] > 0).all()
    assert list(panel["eval_date"].dt.strftime("%Y-%m-%d")) == ["2026-06-03"]
