import datetime as dt

import pandas as pd
import pytest

from app.data.broker_adapter import HealthCheckResult
import numpy as np

import app.data.pykrx_client as pykrx_client
from app.data.pykrx_client import (
    PykrxClient,
    PrefetchBundle,
    HealthResult,
    compute_h_ref,
    compute_atr20,
    compute_avg_value_20d,
    prefetch_final,
    prefetch_top_value,
    select_top_value_universe,
    fetch_confirmed_close,
    health_check,
    overnight_gap_stats,
    latest_trading_day,
    market_breadth,
    sector_changes,
    market_investors,
    market_overview,
    kospi_index_curve,
    supply_5d,
)


class FakePykrx:
    """주입형 가짜 pykrx 모듈 — 네트워크 없음, 호출 기록."""

    def __init__(self):
        self.calls: list[tuple] = []
        self.ohlcv_df: pd.DataFrame | None = None
        # (market, investor) → 순매수거래대금 프레임. 외인/기관 유형별로 분리.
        self.net_frames: dict[tuple[str, str], pd.DataFrame] = {}
        self.ticker_list: list[str] = []

    def get_market_ticker_list(self, date, market="ALL"):
        self.calls.append(("ticker_list", date, market))
        return list(self.ticker_list)

    def get_market_ohlcv(self, fromdate, todate, ticker):
        self.calls.append(("ohlcv", fromdate, todate, ticker))
        return self.ohlcv_df

    def get_market_net_purchases_of_equities(self, fromdate, todate, market, investor):
        self.calls.append(("net", fromdate, todate, market, investor))
        return self.net_frames.get((market, investor))

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


# ── 수급: 시장×투자자유형별 1회=총 4회, value 컬럼 합산, per-ticker 금지 ──
def test_net_purchases_four_calls_value_column_sums_investors():
    px = FakePykrx()
    # 외인/기관 유형별로 분리 — 종목별로 두 유형을 합산해야 한다.
    px.net_frames[("KOSPI", "외국인")] = pd.DataFrame(
        {"순매수거래대금": [5_000_000_000], "순매수거래량": [1]},
        index=["000660"])
    px.net_frames[("KOSPI", "기관합계")] = pd.DataFrame(
        {"순매수거래대금": [3_000_000_000], "순매수거래량": [1]},
        index=["000660"])
    px.net_frames[("KOSDAQ", "외국인")] = pd.DataFrame(
        {"순매수거래대금": [-3_000_000_000], "순매수거래량": [1]},
        index=["035720"])
    px.net_frames[("KOSDAQ", "기관합계")] = pd.DataFrame(
        {"순매수거래대금": [1_000_000_000], "순매수거래량": [1]},
        index=["035720"])
    client = PykrxClient(px)
    result = client.get_net_purchases("20260629", "20260629")
    net_calls = [c for c in px.calls if c[0] == "net"]
    assert len(net_calls) == 4                      # 2시장 × 2투자자유형 = 4회
    assert {c[3] for c in net_calls} == {"KOSPI", "KOSDAQ"}      # 두 시장 모두
    assert {c[4] for c in net_calls} == {"외국인", "기관합계"}  # 두 투자자유형
    # 외인+기관 순매수거래대금(value) 종목별 합산
    assert result["000660"] == 8_000_000_000.0      # 5e9 + 3e9
    assert result["035720"] == -2_000_000_000.0     # -3e9 + 1e9 (양방향)


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
    # 외인+기관 순매수거래대금 합산: 000660 = 5e9 + 3e9 = 8e9
    px.net_frames[("KOSPI", "외국인")] = _supply("000660", 5_000_000_000)
    px.net_frames[("KOSPI", "기관합계")] = _supply("000660", 3_000_000_000)
    px.net_frames[("KOSDAQ", "외국인")] = _supply("035720", -1_000_000_000)
    px.net_frames[("KOSDAQ", "기관합계")] = _supply("035720", -1_000_000_000)
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
    assert len(net_calls) == 4                       # 시장(2) × 투자자(외국인·기관합계)
    assert {c[3] for c in net_calls} == {"KOSPI", "KOSDAQ"}
    assert {c[4] for c in net_calls} == {"외국인", "기관합계"}


# ── T1: D-1 거래대금 상위 200 유니버스 선정 ──────────────
class _FakeByTickerPx:
    """select_top_value_universe 전용 fake — 시장별 종목 거래대금 스냅샷 제공."""

    def __init__(self, frames):
        self.frames = frames                          # market_name → df
        self.calls: list[tuple] = []

    def get_market_ohlcv_by_ticker(self, date, market="ALL"):
        self.calls.append((date, market))
        return self.frames.get(market)


def _by_ticker_df(pairs):
    idx = [t for t, _ in pairs]
    return pd.DataFrame({"거래대금": [v for _, v in pairs]}, index=idx)


def test_select_top_value_universe_ranks_union_of_markets():
    px = _FakeByTickerPx({
        "KOSPI": _by_ticker_df([("000660", 900), ("005930", 500)]),
        "KOSDAQ": _by_ticker_df([("035720", 800), ("247540", 100)]),
    })
    tickers, market_of = select_top_value_universe(px, "20260629", top_n=3)
    # 거래대금 내림차순 union → 900, 800, 500 (247540=100 컷)
    assert tickers == ["000660", "035720", "005930"]
    assert market_of == {"000660": "KOSPI", "035720": "KOSDAQ", "005930": "KOSPI"}
    assert {c[1] for c in px.calls} == {"KOSPI", "KOSDAQ"}   # 시장별 1회


def test_select_top_value_universe_graceful_on_missing_market():
    px = _FakeByTickerPx({"KOSPI": _by_ticker_df([("000660", 900)])})  # KOSDAQ None
    tickers, market_of = select_top_value_universe(px, "20260629", top_n=200)
    assert tickers == ["000660"]
    assert market_of == {"000660": "KOSPI"}


def test_prefetch_top_value_limits_universe_and_carries_market():
    px = _FakeByTickerPx({
        "KOSPI": _by_ticker_df([("000660", 900)]),
        "KOSDAQ": _by_ticker_df([("035720", 800)]),
    })
    # OHLCV/수급/지수는 top_value 경로에서도 필요 — 같은 fake 에 메서드 확장
    px.ohlcv = _ohlcv(["20260626", "20260629"], [100, 120], [90, 110], [95, 115], [10, 20])
    px.get_market_ohlcv = lambda frm, to, ticker: px.ohlcv
    px.get_market_net_purchases_of_equities = lambda frm, to, mkt, inv: _supply("000660", 8e9)
    px.get_index_ohlcv = lambda frm, to, code: px.ohlcv
    bundle = prefetch_top_value(dt.date(2026, 6, 30), px, top_n=200)
    assert isinstance(bundle, PrefetchBundle)
    assert set(bundle.universe) == {"000660", "035720"}     # top200 union (여기선 2종목)
    assert bundle.market_of["000660"] == "KOSPI"
    assert bundle.market_of["035720"] == "KOSDAQ"


# ── 오버나잇 갭 통계: gap[t]=open[t+1]/close[t]-1 ──────────
class _FakeGapPx:
    """overnight_gap_stats 전용 주입 fake — 시가/종가 프레임 반환."""

    def __init__(self, opens, closes):
        self.opens = opens
        self.closes = closes
        self.calls: list[tuple] = []

    def get_market_ohlcv(self, fromdate, todate, ticker):
        self.calls.append(("ohlcv", fromdate, todate, ticker))
        if not self.opens:
            return None
        idx = pd.RangeIndex(len(self.opens))
        return pd.DataFrame({"시가": self.opens, "종가": self.closes}, index=idx)


def test_overnight_gap_stats_constant_gaps():
    # 21행 → 20갭, 모든 갭 = 102/100-1 = 0.02 (손검증 가능)
    closes = [100.0] * 21
    opens = [0.0] + [102.0] * 20            # opens[0]은 갭 산출에 미사용
    px = _FakeGapPx(opens, closes)
    res = overnight_gap_stats("000660", dt.date(2026, 6, 30), pykrx_module=px)
    assert res["n"] == 20
    assert res["mean"] == pytest.approx(0.02)
    assert res["std"] == pytest.approx(0.0)         # 동일 갭 → 모σ=0
    assert res["worst5pct"] == pytest.approx(0.02)
    # 룩어헤드 금지: todate=asof(20260630)
    assert px.calls[-1][2] == "20260630"


def test_overnight_gap_stats_matches_numpy_moments():
    # 26행 → 25갭, 변동 있는 시가로 mean/모σ/5퍼센타일 numpy 대조
    closes = [100.0 + i for i in range(26)]
    opens = [0.0] + [closes[i] * (1.0 + (((i % 5) - 2) / 100.0)) for i in range(25)]
    px = _FakeGapPx(opens, closes)
    res = overnight_gap_stats("000660", dt.date(2026, 6, 30), pykrx_module=px)
    o = np.array(opens, dtype=float)
    c = np.array(closes, dtype=float)
    gaps = o[1:] / c[:-1] - 1.0
    assert res["n"] == 25
    assert res["mean"] == pytest.approx(float(gaps.mean()))
    assert res["std"] == pytest.approx(float(gaps.std()))            # 모표준편차
    assert res["worst5pct"] == pytest.approx(float(np.percentile(gaps, 5)))


def test_overnight_gap_stats_respects_lookback_window():
    # 40갭이지만 lookback_days=20 → 최근 20갭만 사용 → n=20
    closes = [100.0] * 41
    opens = [0.0] + [101.0] * 40
    px = _FakeGapPx(opens, closes)
    res = overnight_gap_stats("000660", dt.date(2026, 6, 30), lookback_days=20, pykrx_module=px)
    assert res["n"] == 20
    assert res["mean"] == pytest.approx(0.01)


def test_overnight_gap_stats_none_on_short_history():
    # 10행 → 9갭 <20 → None
    closes = [100.0] * 10
    opens = [0.0] + [101.0] * 9
    px = _FakeGapPx(opens, closes)
    assert overnight_gap_stats("000660", dt.date(2026, 6, 30), pykrx_module=px) is None


def test_overnight_gap_stats_none_on_empty():
    px = _FakeGapPx([], [])
    assert overnight_gap_stats("000660", dt.date(2026, 6, 30), pykrx_module=px) is None


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


class _PxHealthDateAware:
    """수급이 조회 날짜(todate)에 따라 달라지는 fake — 주말/휴일 단일일 조회는 빈값."""

    def __init__(self, index_df, supply_by_day, empty_days):
        self.index_df = index_df
        self.supply_by_day = supply_by_day
        self.empty_days = empty_days

    def get_index_ohlcv(self, fromdate, todate, index_code):
        return self.index_df   # 범위 조회 → 실제 마지막 거래일까지 포함(엔드포인트 무시)

    def get_market_net_purchases_of_equities(self, fromdate, todate, market, investor):
        if todate in self.empty_days:
            return pd.DataFrame()          # 무거래일 단일 조회 → 빈 프레임
        return self.supply_by_day[todate][market]


def test_health_check_uses_last_trading_day_for_supply_not_calendar_d1():
    # 월요일(2026-07-06) 실행: 달력 D-1 = 일요일(07-05, 무거래) → 그 날짜로 수급을 조회하면
    # 빈값이라 오탐 BLOCKED. 지수 범위 조회가 해소한 실제 마지막 거래일(07-03)로 수급을
    # 조회해야 정상 통과한다. (월요일·연휴 다음날 fail-closed 오탐 회귀 방지)
    px = _PxHealthDateAware(
        index_df=_index_df(130, "20260703"),
        supply_by_day={"20260703": {"KOSPI": _supply("000660", 8e9),
                                    "KOSDAQ": _supply("035720", 1e9)}},
        empty_days={"20260705"},
    )
    res = health_check(px, today=dt.date(2026, 7, 6), min_rows=120)
    assert res.ok is True
    assert res.latest_trading_day == dt.date(2026, 7, 3)


def test_stock_names_bulk_maps_ticker_to_name_from_price_change():
    # get_market_price_change 의 '종목명' 컬럼에서 ticker→종목명 벌크 맵을 만든다
    # (개별 get_market_ticker_name 200회 회피). KOSPI∪KOSDAQ 2회 조회.
    from app.data.pykrx_client import pykrx_market_name, Market, stock_names_bulk
    by_market = {
        pykrx_market_name(Market.KOSPI): _price_change_df("000660", "SK하이닉스"),
        pykrx_market_name(Market.KOSDAQ): _price_change_df("086520", "에코프로"),
    }

    class _PxNames:
        def get_market_price_change(self, frm, to, market):
            return by_market.get(market)

    names = stock_names_bulk("20260620", "20260703", pykrx_module=_PxNames())
    assert names == {"000660": "SK하이닉스", "086520": "에코프로"}


def _price_change_df(ticker, name):
    return pd.DataFrame({"종목명": [name], "거래대금": [1]}, index=[ticker])


class _HangingPrefetchPx:
    """prefetch_final용 fake — 특정 티커에서 무한 대기(hang) 모사."""

    def __init__(self, hang_ticker, hang_sec, ohlcv_df):
        self.hang_ticker = hang_ticker
        self.hang_sec = hang_sec
        self.ohlcv_df = ohlcv_df

    def get_market_ohlcv(self, frm, to, ticker):
        if ticker == self.hang_ticker:
            import time
            time.sleep(self.hang_sec)          # 응답 없는 종목 모사
        return self.ohlcv_df

    def get_market_net_purchases_of_equities(self, frm, to, market, investor):
        return _supply("000660", 8e9)

    def get_index_ohlcv(self, frm, to, index_code):
        return self.ohlcv_df


def test_prefetch_final_skips_hanging_ticker_without_blocking(monkeypatch):
    # 200종목 순회 중 한 종목이 응답 없이 멈춰도 전체 배치가 그 종목에 갇히지 않고
    # 타임아웃 스킵 후 진행해야 한다(장전 프리페치 무한 대기 회귀 방지).
    import time
    good = _ohlcv(["1", "2", "3"], [100, 200, 150],
                  [90, 180, 140], [95, 190, 145], [1, 1, 1])
    px = _HangingPrefetchPx(hang_ticker="HANG", hang_sec=5.0, ohlcv_df=good)
    monkeypatch.setattr(pykrx_client, "OHLCV_TIMEOUT_SEC", 0.2)
    t0 = time.monotonic()
    bundle = prefetch_final(dt.date(2026, 7, 6), pykrx_module=px,
                            universe=["HANG", "000660"])
    elapsed = time.monotonic() - t0
    assert elapsed < 3.0                       # 5초 hang을 기다리지 않고 스킵
    assert "HANG" not in bundle.h_ref_252      # 무응답 종목은 제외
    assert "000660" in bundle.h_ref_252        # 정상 종목은 포함


# ── /market: breadth(시장 폭) + sectors(업종 등락) ─────────
class _FakeMarketPx:
    """market_* 전용 주입 fake — 스냅샷/업종지수/최근거래일 제공."""

    def __init__(self, snapshot=None, sector_dfs=None, nearest="20260630"):
        self.snapshot = snapshot
        self.sector_dfs = sector_dfs or {}
        self.nearest = nearest

    def get_nearest_business_day_in_a_week(self, *args, **kw):
        return self.nearest

    def get_market_ohlcv_by_ticker(self, date, market="ALL"):
        return self.snapshot

    def get_index_ohlcv(self, fromdate, todate, index_code):
        return self.sector_dfs.get(index_code)


def _snapshot():
    # 등락률 부호로 adv/dec/unchanged; +29↑ 상한가; 종가>=고가 신고가 근사
    return pd.DataFrame(
        {
            "고가": [100.0, 100.0, 100.0, 100.0, 100.0],
            "종가": [100.0, 90.0, 100.0, 80.0, 70.0],
            "등락률": [1.5, -0.5, 0.0, 30.0, 29.5],
        },
        index=["000660", "005930", "035720", "091990", "247540"],
    )


def _sector_df(prev, last):
    return pd.DataFrame({"종가": [float(prev), float(last)]}, index=["20260629", "20260630"])


def test_latest_trading_day_parses_nearest_business_day():
    px = _FakeMarketPx(nearest="20260630")
    assert latest_trading_day(px) == dt.date(2026, 6, 30)


def test_market_breadth_counts_by_sign_and_limits():
    px = _FakeMarketPx(snapshot=_snapshot())
    b = market_breadth(dt.date(2026, 6, 30), px)
    assert b["advancers"] == 3          # 1.5, 30.0, 29.5
    assert b["decliners"] == 1          # -0.5
    assert b["unchanged"] == 1          # 0.0
    assert b["limit_ups"] == 2          # >=29.0 → 30.0, 29.5
    assert b["new_highs"] == 2          # 종가>=고가 → 100/100, 100/100


def test_market_breadth_empty_snapshot_returns_zeros():
    px = _FakeMarketPx(snapshot=None)
    b = market_breadth(dt.date(2026, 6, 30), px)
    assert b == {"advancers": 0, "decliners": 0, "unchanged": 0,
                 "new_highs": 0, "limit_ups": 0}


def test_sector_changes_sorted_desc_close_to_close():
    px = _FakeMarketPx(sector_dfs={
        "1013": _sector_df(100.0, 110.0),   # 전기전자 +10%
        "1008": _sector_df(100.0, 95.0),    # 화학 -5%
    })
    out = sector_changes(dt.date(2026, 6, 30), px)
    assert [s["name"] for s in out] == ["전기전자", "화학"]   # 내림차순
    assert out[0]["change_pct"] == pytest.approx(10.0)
    assert out[1]["change_pct"] == pytest.approx(-5.0)


def test_sector_changes_empty_when_no_index_data():
    px = _FakeMarketPx(sector_dfs={})
    assert sector_changes(dt.date(2026, 6, 30), px) == []


# ── /market: investors(투자자별 수급, 억 단위) ─────────────
class _FakeInvestorPx(_FakeMarketPx):
    """market_investors 전용 fake — 시장별 투자자 순매수 프레임 제공."""

    def __init__(self, investor_dfs=None, raises=False, **kw):
        super().__init__(**kw)
        self.investor_dfs = investor_dfs or {}
        self.raises = raises
        self.investor_calls: list[tuple] = []

    def get_market_trading_value_by_investor(self, fromdate, todate, market):
        self.investor_calls.append((fromdate, todate, market))
        if self.raises:
            raise ConnectionError("investor outage")
        return self.investor_dfs.get(market)


def _investor_df(foreign, institution, individual):
    # pykrx 순매수 컬럼(원 단위). 인덱스=투자자 구분.
    return pd.DataFrame(
        {"순매수": [float(individual), float(foreign), float(institution)]},
        index=["개인", "외국인", "기관합계"],
    )


def test_market_investors_sums_markets_in_eok():
    px = _FakeInvestorPx(investor_dfs={
        "KOSPI": _investor_df(foreign=30_000_000_000, institution=-10_000_000_000,
                              individual=-20_000_000_000),
        "KOSDAQ": _investor_df(foreign=10_000_000_000, institution=5_000_000_000,
                               individual=-15_000_000_000),
    })
    inv = market_investors(dt.date(2026, 6, 30), px)
    # 억 단위(÷1e8): 외인 (300+100)=400, 기관 (-100+50)=-50, 개인 (-200-150)=-350
    assert inv["foreign_net"] == pytest.approx(400.0)
    assert inv["institution_net"] == pytest.approx(-50.0)
    assert inv["individual_net"] == pytest.approx(-350.0)
    # 시장별 1회 = 총 2회
    assert {c[2] for c in px.investor_calls} == {"KOSPI", "KOSDAQ"}


def test_market_investors_graceful_zero_on_outage():
    px = _FakeInvestorPx(raises=True)
    inv = market_investors(dt.date(2026, 6, 30), px)
    assert inv == {"foreign_net": 0.0, "institution_net": 0.0, "individual_net": 0.0}


def test_market_investors_zero_when_no_frame():
    px = _FakeInvestorPx(investor_dfs={})
    inv = market_investors(dt.date(2026, 6, 30), px)
    assert inv == {"foreign_net": 0.0, "institution_net": 0.0, "individual_net": 0.0}


def test_market_overview_combines_breadth_and_sectors():
    px = _FakeInvestorPx(snapshot=_snapshot(),
                         sector_dfs={"1013": _sector_df(100.0, 110.0)},
                         nearest="20260630",
                         investor_dfs={
                             "KOSPI": _investor_df(30_000_000_000, -10_000_000_000,
                                                   -20_000_000_000),
                             "KOSDAQ": _investor_df(10_000_000_000, 5_000_000_000,
                                                    -15_000_000_000),
                         })
    data = market_overview(px)
    assert data["asof"] == dt.date(2026, 6, 30)
    assert data["breadth"]["advancers"] == 3
    assert data["sectors"][0]["name"] == "전기전자"
    assert data["investors"]["foreign_net"] == pytest.approx(400.0)


# ── S1: KOSPI 벤치마크 누적수익 곡선 ───────────────────────
class _FakeIndexPx:
    """kospi_index_curve 전용 fake — KOSPI 지수 종가 프레임 제공."""

    def __init__(self, closes=None, raises=False):
        self.closes = closes
        self.raises = raises
        self.calls: list[tuple] = []

    def get_index_ohlcv(self, fromdate, todate, index_code):
        self.calls.append((fromdate, todate, index_code))
        if self.raises:
            raise ConnectionError("index outage")
        if self.closes is None:
            return None
        idx = pd.to_datetime(["2026-06-29", "2026-06-30", "2026-07-01"][:len(self.closes)])
        return pd.DataFrame({"종가": self.closes}, index=idx)


def test_kospi_index_curve_cumulative_return_from_base():
    px = _FakeIndexPx(closes=[100.0, 101.0, 99.0])
    curve = kospi_index_curve(dt.date(2026, 6, 29), dt.date(2026, 7, 1), px)
    assert [p["cum"] for p in curve] == pytest.approx([0.0, 0.01, -0.01])
    assert curve[0]["date"] == "2026-06-29"
    assert px.calls[-1] == ("20260629", "20260701", "1001")     # KOSPI pykrx code


def test_kospi_index_curve_empty_when_no_data():
    assert kospi_index_curve(dt.date(2026, 6, 29), dt.date(2026, 7, 1), _FakeIndexPx(None)) == []


def test_kospi_index_curve_empty_on_outage():
    assert kospi_index_curve(dt.date(2026, 6, 29), dt.date(2026, 7, 1),
                             _FakeIndexPx(raises=True)) == []


# ── S2: 종목별 5일 수급(외인·기관 순매수 거래대금, 억) ──────
class _FakeSupplyPx:
    """supply_5d 전용 fake — 종목별 투자자 순매수 거래대금 프레임 제공."""

    def __init__(self, df=None, raises=False):
        self.df = df
        self.raises = raises
        self.calls: list[tuple] = []

    def get_market_trading_value_by_date(self, fromdate, todate, ticker):
        self.calls.append((fromdate, todate, ticker))
        if self.raises:
            raise ConnectionError("supply outage")
        return self.df


def _supply5d_df(rows=5):
    dates = ["2026-06-24", "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30"]
    idx = pd.to_datetime(dates[:rows])
    # 원 단위(÷1e8 억). 외인/기관 순매수 거래대금.
    return pd.DataFrame(
        {"외국인합계": [1e8, -2e8, 3e8, 0.0, 5e8][:rows],
         "기관합계": [-1e8, 2e8, -3e8, 4e8, -5e8][:rows]},
        index=idx,
    )


def test_supply_5d_returns_last_5_days_in_eok():
    px = _FakeSupplyPx(df=_supply5d_df())
    res = supply_5d("000660", dt.date(2026, 6, 30), px)
    assert res["dates"] == ["2026-06-24", "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30"]
    assert res["foreign"] == pytest.approx([1.0, -2.0, 3.0, 0.0, 5.0])
    assert res["institution"] == pytest.approx([-1.0, 2.0, -3.0, 4.0, -5.0])
    assert px.calls[-1][1] == "20260630"                        # todate=asof(룩어헤드 금지)


def test_supply_5d_takes_only_last_5_when_more_rows():
    idx = pd.to_datetime(["2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25",
                          "2026-06-26", "2026-06-29", "2026-06-30"])
    df = pd.DataFrame({"외국인합계": [9e8] * 7, "기관합계": [-9e8] * 7}, index=idx)
    res = supply_5d("000660", dt.date(2026, 6, 30), _FakeSupplyPx(df=df))
    assert len(res["dates"]) == 5
    assert res["dates"][0] == "2026-06-24"                      # 최근 5거래일만


def test_supply_5d_none_on_empty():
    assert supply_5d("000660", dt.date(2026, 6, 30), _FakeSupplyPx(None)) is None


def test_supply_5d_none_on_outage():
    assert supply_5d("000660", dt.date(2026, 6, 30), _FakeSupplyPx(raises=True)) is None


# ── 상장주식 집합·종목명 헬퍼(신고가 위젯 빈 화면 수정) ──────────────────


class _FakePykrxListing:
    """상장목록/종목명용 주입형 가짜 pykrx — 네트워크 없음."""

    def __init__(self, tickers=("005930", "122350"), names=None, boom=False):
        self._tickers = list(tickers)
        self._names = names if names is not None else {"005930": "삼성전자"}
        self._boom = boom

    def get_market_ticker_list(self, day_s, market):
        if self._boom:
            raise ConnectionError("KRX outage")
        return list(self._tickers)

    def get_market_ticker_name(self, ticker):
        if self._boom:
            raise ConnectionError("KRX outage")
        # 실측: 미상장 티커(ETF 등)는 문자열이 아니라 빈 DataFrame 을 반환한다
        return self._names.get(ticker, pd.DataFrame())


def _clear_listing_caches():
    pykrx_client._LISTED_CACHE.clear()
    pykrx_client._NAME_CACHE.clear()


def test_filter_listed_stocks_drops_non_stocks():
    _clear_listing_caches()
    rows = [{"ticker": "005930", "name": "삼성전자"},
            {"ticker": "000117", "name": "어떤채권ETF"}]
    out = pykrx_client.filter_listed_stocks(rows, pykrx_module=_FakePykrxListing())
    assert [r["ticker"] for r in out] == ["005930"]
    _clear_listing_caches()


def test_filter_listed_stocks_fail_open_on_error_and_empty():
    _clear_listing_caches()
    rows = [{"ticker": "000117", "name": "어떤채권ETF"}]
    # KRX 조회 실패 → 원본 유지(fail-open)
    assert pykrx_client.filter_listed_stocks(
        rows, pykrx_module=_FakePykrxListing(boom=True)) == rows
    # 빈 상장목록(휴장 등) → 원본 유지
    assert pykrx_client.filter_listed_stocks(
        rows, pykrx_module=_FakePykrxListing(tickers=())) == rows
    _clear_listing_caches()


def test_listed_stock_set_caches_per_day():
    _clear_listing_caches()
    day_s = "20260703"
    first = pykrx_client.listed_stock_set(day_s, pykrx_module=_FakePykrxListing())
    assert "005930" in first
    # 두 번째 호출은 캐시 히트 — 장애 모듈을 줘도 네트워크(예외) 안 탄다
    second = pykrx_client.listed_stock_set(day_s, pykrx_module=_FakePykrxListing(boom=True))
    assert second == first
    _clear_listing_caches()


def test_stock_name_resolves_and_none_for_unlisted():
    _clear_listing_caches()
    px = _FakePykrxListing()
    assert pykrx_client.stock_name("005930", pykrx_module=px) == "삼성전자"
    assert pykrx_client.stock_name("000117", pykrx_module=px) is None   # 빈 DataFrame → None
    # 캐시 히트 — 장애 모듈을 줘도 이미 캐시된 이름 반환
    assert pykrx_client.stock_name(
        "005930", pykrx_module=_FakePykrxListing(boom=True)) == "삼성전자"
    _clear_listing_caches()
