from datetime import timedelta

import pytest

from app.data.broker_adapter import (
    LiveBrokerDataAdapter,
    HealthCheckResult,
    Quote,
    ValueRankEntry,
    IndexLevel,
    compute_coverage,
    is_publishable,
)
from app.data.mapping import Market


class FakePykrxClient:
    def __init__(self):
        self.universe = ["000660"]
        self.net = {"000660": 8e9}
        self.health = HealthCheckResult(True, "20260629", 252)
        self.net_calls: list[tuple[str, str]] = []
        self.last_trading = None          # 주입 시 그 날짜를 D-1 로 사용
    def get_universe(self, date): return self.universe
    def get_ohlcv(self, ticker, fromdate, todate): return ("ohlcv", ticker)
    def get_net_purchases(self, fromdate, todate):
        self.net_calls.append((fromdate, todate))
        return self.net
    def get_index_ohlcv(self, index_code, fromdate, todate):
        return ("index", index_code)
    def health_check(self, df, expected_last_date): return self.health
    def last_trading_day(self, run_date):
        return self.last_trading or (run_date - timedelta(days=1))


class FakeKisClient:
    def __init__(self):
        self.fail_for: set[str] = set()
        self.quotes = {"A": Quote("A", 1, 1, 0.0), "B": Quote("B", 2, 1, 0.0),
                       "C": Quote("C", 3, 1, 0.0)}
    def get_quote(self, ticker):
        if ticker in self.fail_for:
            raise ConnectionError("KIS partial fail")
        return self.quotes[ticker]
    def get_value_ranking(self, market):
        return [ValueRankEntry("000660", 1e11, 1)]
    def get_index_level(self, market): return IndexLevel(market, 2650.0)


class FakeDartClient:
    def __init__(self, veto=1): self.veto = veto
    def dilution_veto(self, ticker, snapshot_at): return self.veto   # 실 DartClient 계약(2-arity)


def _adapter(**kw):
    return LiveBrokerDataAdapter(
        pykrx=FakePykrxClient(), kis=FakeKisClient(),
        dart=FakeDartClient(**kw.pop("dart_kw", {})),
        healthcheck_index_market=Market.KOSPI,
        healthcheck_fromdate="20250629", healthcheck_todate="20260629",
        healthcheck_expected_last="20260629", **kw)


# ── coverage 순수 함수 ────────────────────────────────────
def test_compute_coverage_and_publishable():
    assert compute_coverage(0, 0) == 0.0
    assert compute_coverage(10, 7) == pytest.approx(0.7)
    assert is_publishable(0.70) is True
    assert is_publishable(0.69) is False


# ── 저하모드: 부분 실패 커버리지 < 70% → 미발행 ───────────
def test_bulk_quotes_partial_failure_below_threshold():
    adapter = _adapter()
    adapter._kis.fail_for = {"B"}     # 3개 중 1개 실패 → 2/3 ≈ 0.667
    quotes, coverage = adapter.get_quotes_bulk(["A", "B", "C"])
    assert set(quotes) == {"A", "C"}
    assert coverage == pytest.approx(2 / 3)
    assert is_publishable(coverage) is False


def test_bulk_quotes_full_coverage_publishable():
    adapter = _adapter()
    quotes, coverage = adapter.get_quotes_bulk(["A", "B", "C"])
    assert coverage == 1.0
    assert is_publishable(coverage) is True


# ── 매핑 위임 ─────────────────────────────────────────────
def test_index_ohlcv_maps_market_to_pykrx_code():
    adapter = _adapter()
    assert adapter.get_index_ohlcv(Market.KOSDAQ, "20250101", "20260629") == \
        ("index", "2001")   # KOSDAQ → pykrx 2001


def test_net_purchases_and_universe_delegate():
    adapter = _adapter()
    assert adapter.get_universe("20260629") == ["000660"]
    assert adapter.get_net_purchases("20260629", "20260629") == {"000660": 8e9}


# ── veto fail-closed 위임 ─────────────────────────────────
def test_dilution_veto_delegates_fail_closed():
    adapter = _adapter(dart_kw={"veto": 0})
    assert adapter.get_dilution_veto("999999", "20260629", "20260630") == 0


# ── health_check 위임 ─────────────────────────────────────
def test_health_check_delegates_to_pykrx():
    adapter = _adapter()
    res = adapter.health_check()
    assert res.ok is True
    assert res.last_trading_date == "20260629"


# ── ABC 계약 충족(인스턴스화 가능) ────────────────────────
def test_live_adapter_is_concrete():
    adapter = _adapter()
    assert adapter.get_quote("A").ticker == "A"
    assert adapter.get_value_ranking(Market.KOSPI)[0].ticker == "000660"
    assert adapter.get_index_level(Market.KOSPI).level == 2650.0


# ── T1: build_candidates 캐시 union + OHLCV 재조회 금지 ────
def test_build_candidates_prefetch_union_no_ohlcv_refetch():
    from datetime import date, datetime
    from types import SimpleNamespace

    adapter = _adapter()
    calls = []
    adapter._pykrx.get_ohlcv = lambda t, f, td: calls.append(t)   # 호출되면 기록
    prefetch = {
        "000660": SimpleNamespace(h_ref_252=24000.0, h_ref_60=23500.0, atr20=300.0,
                                  avg_value_20d=5e10, d1_supply_value=8e9, market="KOSPI"),
        "035720": SimpleNamespace(h_ref_252=98000.0, h_ref_60=95000.0, atr20=1500.0,
                                  avg_value_20d=3e10, d1_supply_value=1e9, market="KOSDAQ"),
    }
    cands = adapter.build_candidates(
        date(2026, 6, 30), datetime(2026, 6, 30, 15, 20), prefetch=prefetch)
    tickers = {c.ticker for c in cands}
    assert tickers == {"000660", "035720"}    # 라이브(000660) ∪ 캐시(000660,035720)
    assert calls == []                        # 캐시 종목 → OHLCV 재조회 0회
    by = {c.ticker: c for c in cands}
    assert by["035720"].market == "KOSDAQ"    # 캐시 저장 market 사용
    assert by["035720"].high_60 == 95000.0
    assert by["000660"].market == "KOSPI"     # 라이브 랭킹 market 우선


def test_build_candidates_queries_supply_on_last_trading_day_not_calendar_d1():
    # 월요일(run_date) 의 달력 D-1 은 일요일 — 그 날짜로 수급을 조회하면 전 종목 0 이 되어
    # supply_tilt 가 통째로 중립(1.0)이 된다. 실 거래일(금요일)로 조회해야 한다.
    from datetime import date, datetime
    from types import SimpleNamespace

    adapter = _adapter()
    adapter._pykrx.last_trading = date(2026, 7, 10)      # 금요일
    prefetch = {"000660": SimpleNamespace(h_ref_252=24000.0, h_ref_60=23500.0, atr20=300.0,
                                          avg_value_20d=5e10, d1_supply_value=None,
                                          market="KOSPI")}
    adapter.build_candidates(date(2026, 7, 13),          # 월요일
                             datetime(2026, 7, 13, 15, 20), prefetch=prefetch)
    assert adapter._pykrx.net_calls == [("20260710", "20260710")]   # 일요일(20260712) 아님


def test_build_candidates_carries_live_ranking_names():
    # 랭킹 응답의 종목명을 후보에 실어야 보드/알림이 코드 대신 이름을 보여준다.
    # 랭킹 밖 캐시 종목은 이름원이 없어 티커 유지 — 오케스트레이터가 universe_cache 로 오버레이.
    from datetime import date, datetime
    from types import SimpleNamespace

    adapter = _adapter()
    adapter._kis.get_value_ranking = lambda m: (
        [ValueRankEntry("000660", 1e11, 1, name="SK하이닉스")]
        if m == Market.KOSPI else [])
    prefetch = {
        "000660": SimpleNamespace(h_ref_252=24000.0, h_ref_60=23500.0, atr20=300.0,
                                  avg_value_20d=5e10, d1_supply_value=8e9, market="KOSPI"),
        "035720": SimpleNamespace(h_ref_252=98000.0, h_ref_60=95000.0, atr20=1500.0,
                                  avg_value_20d=3e10, d1_supply_value=1e9, market="KOSDAQ"),
    }
    cands = adapter.build_candidates(
        date(2026, 6, 30), datetime(2026, 6, 30, 15, 20), prefetch=prefetch)
    by = {c.ticker: c for c in cands}
    assert by["000660"].name == "SK하이닉스"
    assert by["035720"].name == "035720"


def test_build_candidates_falls_back_to_ohlcv_without_prefetch():
    import pandas as pd
    from datetime import date, datetime

    adapter = _adapter()
    df = pd.DataFrame({"고가": [100.0] * 60, "저가": [90.0] * 60,
                       "종가": [95.0] * 60, "거래대금": [1e10] * 60})
    calls = []
    adapter._pykrx.get_ohlcv = lambda t, f, td: (calls.append(t), df)[1]
    cands = adapter.build_candidates(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20))
    assert calls == ["000660"]                # prefetch 없음 → 라이브-only OHLCV 폴백
    assert {c.ticker for c in cands} == {"000660"}


def test_build_candidates_unions_volume_surge_fresh_breakouts():
    # US-006: 거래대금순(D-1 유니버스 중복)에 없고 당일 거래증가율(RVOL)순에만 있는
    # '오늘 처음 터진' 신선돌파 종목이 후보풀에 순증해야 한다.
    import pandas as pd
    from datetime import date, datetime

    adapter = _adapter()
    adapter._kis.get_volume_surge_ranking = lambda m: [ValueRankEntry("247540", 5e9, 1)]
    df = pd.DataFrame({"고가": [100.0] * 60, "저가": [90.0] * 60,
                       "종가": [95.0] * 60, "거래대금": [1e10] * 60})
    adapter._pykrx.get_ohlcv = lambda t, f, td: df
    cands = adapter.build_candidates(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20))
    tickers = {c.ticker for c in cands}
    assert "000660" in tickers        # 거래대금순 레그(기존)
    assert "247540" in tickers        # 신선돌파(당일 RVOL) 레그 순증


def test_build_candidates_graceful_without_surge_support():
    # KIS 클라이언트가 surge 랭킹을 노출하지 않아도(구버전 fake) 후보 구성이 깨지지 않는다.
    import pandas as pd
    from datetime import date, datetime

    adapter = _adapter()                 # FakeKisClient 에 get_volume_surge_ranking 없음
    df = pd.DataFrame({"고가": [100.0] * 60, "저가": [90.0] * 60,
                       "종가": [95.0] * 60, "거래대금": [1e10] * 60})
    adapter._pykrx.get_ohlcv = lambda t, f, td: df
    cands = adapter.build_candidates(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20))
    assert {c.ticker for c in cands} == {"000660"}   # surge 없이도 거래대금순 레그 정상
