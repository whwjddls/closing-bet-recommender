import datetime as dt

import pandas as pd
import pytest

from app.data.broker_adapter import HealthCheckResult
from app.data.pykrx_client import (
    PykrxClient,
    PrefetchBundle,
    HealthResult,
    compute_h_ref,
    compute_atr20,
    compute_avg_value_20d,
    prefetch_final,
    fetch_confirmed_close,
    health_check,
)


class FakePykrx:
    """주입형 가짜 pykrx 모듈 — 네트워크 없음, 호출 기록."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.ohlcv_df: pd.DataFrame | None = None
        self.net_frames: dict[str, pd.DataFrame] = {}
        self.ticker_list: list[str] = []

    def get_market_ticker_list(self, date, market="ALL"):
        self.calls.append(("ticker_list", date, market))
        return list(self.ticker_list)

    def get_market_ohlcv(self, fromdate, todate, ticker):
        self.calls.append(("ohlcv", fromdate, todate, ticker))
        return self.ohlcv_df

    def get_market_net_purchases_of_equities(self, fromdate, todate, market, investor):
        self.calls.append(("net", fromdate, todate, market, investor))
        return self.net_frames[market]

    def get_index_ohlcv(self, fromdate, todate, index_code):
        self.calls.append(("index", fromdate, todate, index_code))
        return self.ohlcv_df


def _ohlcv(dates, highs, lows, closes, values):
    return pd.DataFrame(
        {"고가": highs, "저가": lows, "종가": closes, "거래대금": values},
        index=dates,
    )


# ── 순수 함수 ─────────────────────────────────────────────
def test_compute_h_ref_uses_only_last_window_highs():
    df = _ohlcv(["1", "2", "3", "4"], [100, 200, 150, 130],
                [90, 180, 140, 120], [95, 190, 145, 125], [1, 1, 1, 1])
    # window=2 → 마지막 2개(150,130) 중 max
    assert compute_h_ref(df, 2) == 150.0
    assert compute_h_ref(df, 4) == 200.0


def test_compute_atr20():
    # 5행, window=2 → 마지막 2개 TR 평균
    df = _ohlcv(["1", "2", "3"], [110, 120, 130], [100, 105, 115],
                [105, 115, 125], [1, 1, 1])
    # TR2 = max(120-105, |120-105|, |105-105|)=15 ; TR3 = max(130-115, |130-115|, |115-115|)=15
    assert compute_atr20(df, window=2) == 15.0


def test_compute_avg_value_20d():
    df = _ohlcv(["1", "2", "3"], [1, 1, 1], [1, 1, 1], [1, 1, 1],
                [100, 200, 300])
    assert compute_avg_value_20d(df, window=2) == 250.0


# ── 생존편향: point-in-time 티커리스트 ────────────────────
def test_get_universe_passes_through_as_of_date():
    px = FakePykrx()
    px.ticker_list = ["000660", "005930"]
    client = PykrxClient(px)
    result = client.get_universe("20260629")
    assert result == ["000660", "005930"]
    assert px.calls[-1] == ("ticker_list", "20260629", "ALL")


# ── 룩어헤드: todate=D-1 그대로 전달, 당일 미요청 ─────────
def test_get_ohlcv_forwards_exact_todate_no_lookahead():
    px = FakePykrx()
    px.ohlcv_df = _ohlcv(["20260629"], [100], [90], [95], [1])
    client = PykrxClient(px)
    client.get_ohlcv("000660", "20250629", "20260629")
    assert px.calls[-1] == ("ohlcv", "20250629", "20260629", "000660")


# ── 수급: 시장별 1회=총 2회, value 컬럼, per-ticker 금지 ──
def test_net_purchases_two_calls_value_column_no_per_ticker():
    px = FakePykrx()
    px.net_frames["KOSPI"] = pd.DataFrame(
        {"순매수거래대금": [8_000_000_000], "순매수거래량": [1]},
        index=["000660"])
    px.net_frames["KOSDAQ"] = pd.DataFrame(
        {"순매수거래대금": [-2_000_000_000], "순매수거래량": [1]},
        index=["035720"])
    client = PykrxClient(px)
    result = client.get_net_purchases("20260629", "20260629")
    net_calls = [c for c in px.calls if c[0] == "net"]
    assert len(net_calls) == 2                      # 시장별 1회 = 총 2회
    assert {c[3] for c in net_calls} == {"KOSPI", "KOSDAQ"}
    assert result["000660"] == 8_000_000_000.0      # value(거래대금) 컬럼
    assert result["035720"] == -2_000_000_000.0     # 양방향


# ── 헬스체크: stale / 행수 부족 → fail-closed ─────────────
def test_health_check_ok():
    px = FakePykrx()
    df = _ohlcv([str(i) for i in range(130)], [1] * 130, [1] * 130,
                [1] * 130, [1] * 130)
    df.index = list(range(129)) + ["20260629"]
    client = PykrxClient(px, min_rows=120)
    res = client.health_check(df, expected_last_date="20260629")
    assert isinstance(res, HealthCheckResult)
    assert res.ok is True


def test_health_check_stale_is_fail_closed():
    px = FakePykrx()
    df = _ohlcv([str(i) for i in range(130)], [1] * 130, [1] * 130,
                [1] * 130, [1] * 130)
    df.index = list(range(129)) + ["20260626"]
    client = PykrxClient(px, min_rows=120)
    res = client.health_check(df, expected_last_date="20260629")
    assert res.ok is False
    assert "stale" in res.reason


def test_health_check_insufficient_rows_is_fail_closed():
    px = FakePykrx()
    df = _ohlcv(["1", "2"], [1, 1], [1, 1], [1, 1], [1, 1])
    client = PykrxClient(px, min_rows=120)
    res = client.health_check(df, expected_last_date="2")
    assert res.ok is False
    assert "rows" in res.reason


def test_health_check_empty_is_fail_closed():
    px = FakePykrx()
    res = PykrxClient(px).health_check(None, expected_last_date="20260629")
    assert res.ok is False


# ── 모듈 정본 인터페이스(00 §2): prefetch_final / fetch_confirmed_close / health_check ──
def _supply(ticker, value):
    return pd.DataFrame({"순매수거래대금": [value], "순매수거래량": [1]},
                        index=[ticker])


def test_fetch_confirmed_close_reads_single_day_close():
    px = FakePykrx()
    px.ohlcv_df = _ohlcv(["20260701"], [110], [100], [105], [9])
    close = fetch_confirmed_close("000660", dt.date(2026, 7, 1), px)
    assert close == 105.0
    assert px.calls[-1] == ("ohlcv", "20260701", "20260701", "000660")


def test_prefetch_final_no_lookahead_todate_is_d_minus_1():
    px = FakePykrx()
    px.ticker_list = ["000660"]
    px.ohlcv_df = _ohlcv(["20260626", "20260629"], [100, 120], [90, 110],
                         [95, 115], [10, 20])
    px.net_frames["KOSPI"] = _supply("000660", 8_000_000_000)
    px.net_frames["KOSDAQ"] = _supply("035720", -2_000_000_000)
    bundle = prefetch_final(dt.date(2026, 6, 30), px)
    assert isinstance(bundle, PrefetchBundle)
    # 룩어헤드 금지: 종목 ohlcv todate=D-1(20260629), 당일(20260630) 미요청
    ohlcv_calls = [c for c in px.calls if c[0] == "ohlcv"]
    assert ohlcv_calls and all(c[2] == "20260629" for c in ohlcv_calls)
    assert bundle.h_ref_60["000660"] == 120.0
    assert "000660" in bundle.avg_value_20d
    assert bundle.net_purchases["000660"] == 8_000_000_000.0
    assert set(bundle.index_ma5) == {"KOSPI", "KOSDAQ"}


def test_prefetch_final_net_purchases_two_market_calls():
    px = FakePykrx()
    px.ticker_list = ["000660"]
    px.ohlcv_df = _ohlcv(["20260626", "20260629"], [100, 120], [90, 110],
                         [95, 115], [10, 20])
    px.net_frames["KOSPI"] = _supply("000660", 8e9)
    px.net_frames["KOSDAQ"] = _supply("035720", -2e9)
    prefetch_final(dt.date(2026, 6, 30), px)
    net_calls = [c for c in px.calls if c[0] == "net"]
    assert len(net_calls) == 2


class _PxHealth:
    """health_check 전용 주입 fake — 지수/수급 분리, 수급 outage 모사."""

    def __init__(self, index_df, net_frames, raise_net=False):
        self.index_df = index_df
        self.net_frames = net_frames
        self.raise_net = raise_net

    def get_index_ohlcv(self, fromdate, todate, index_code):
        return self.index_df

    def get_market_net_purchases_of_equities(self, fromdate, todate, market, investor):
        if self.raise_net:
            raise ConnectionError("supply outage")
        return self.net_frames[market]


def _index_df(n, last):
    idx = [str(i) for i in range(n - 1)] + [last]
    return _ohlcv(idx, [1] * n, [1] * n, [1] * n, [1] * n)


def test_health_check_ok_index_and_supply():
    px = _PxHealth(_index_df(130, "20260629"),
                   {"KOSPI": _supply("000660", 8e9),
                    "KOSDAQ": _supply("035720", 1e9)})
    res = health_check(px, today=dt.date(2026, 6, 30), min_rows=120)
    assert isinstance(res, HealthResult)
    assert res.ok is True
    assert res.latest_trading_day == dt.date(2026, 6, 29)
    assert res.rows == 130


def test_health_check_fail_closed_on_supply_outage():
    px = _PxHealth(_index_df(130, "20260629"), {}, raise_net=True)
    res = health_check(px, today=dt.date(2026, 6, 30), min_rows=120)
    assert res.ok is False                              # D-1 수급 결손 → 런 차단
    assert "수급" in res.detail


def test_health_check_fail_closed_on_insufficient_rows():
    px = _PxHealth(_index_df(10, "20260629"),
                   {"KOSPI": _supply("000660", 8e9),
                    "KOSDAQ": _supply("035720", 1e9)})
    res = health_check(px, today=dt.date(2026, 6, 30), min_rows=120)
    assert res.ok is False
    assert "rows" in res.detail
