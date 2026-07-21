import inspect

import pytest

from app.data.broker_adapter import (
    BrokerDataAdapter,
    Quote,
    ValueRankEntry,
    IndexLevel,
    HealthCheckResult,
)
from app.data.mapping import Market


def test_abc_cannot_be_instantiated():
    with pytest.raises(TypeError):
        BrokerDataAdapter()


def test_required_method_signatures_are_pinned():
    expected = {
        "get_universe": ["self", "date"],
        "get_ohlcv": ["self", "ticker", "fromdate", "todate"],
        "get_net_purchases": ["self", "fromdate", "todate"],
        "get_index_ohlcv": ["self", "market", "fromdate", "todate"],
        "health_check": ["self"],
        "get_value_ranking": ["self", "market"],
        "get_index_level": ["self", "market"],
        "get_quote": ["self", "ticker"],
        "get_dilution_veto": ["self", "ticker", "bgn_de", "end_de"],
    }
    for name, params in expected.items():
        method = getattr(BrokerDataAdapter, name)
        assert list(inspect.signature(method).parameters) == params, name


def test_concrete_subclass_must_implement_all():
    class Partial(BrokerDataAdapter):
        pass

    with pytest.raises(TypeError):
        Partial()


def test_fake_adapter_satisfies_contract():
    class FakeAdapter(BrokerDataAdapter):
        def get_universe(self, date): return ["000660"]
        def get_ohlcv(self, ticker, fromdate, todate): return None
        def get_net_purchases(self, fromdate, todate): return {"000660": 8e9}
        def get_index_ohlcv(self, market, fromdate, todate): return None
        def health_check(self): return HealthCheckResult(True, "20260629", 252)
        def get_value_ranking(self, market):
            return [ValueRankEntry("000660", 1.0e11, 1)]
        def get_index_level(self, market):
            return IndexLevel(market, 2650.0)
        def get_quote(self, ticker):
            return Quote(ticker, 24500.0, 1234567, 5.2)
        def get_dilution_veto(self, ticker, bgn_de, end_de): return 1

    adapter = FakeAdapter()
    assert adapter.get_quote("000660").price == 24500.0
    assert adapter.get_index_level(Market.KOSPI).level == 2650.0
    assert adapter.health_check().ok is True
    assert adapter.get_dilution_veto("000660", "20260629", "20260630") == 1


def test_quote_overheated_default_false():
    q = Quote("000660", 24500.0, 100, 5.2)
    assert q.overheated is False
    assert q.halted is False


# ── off-by-2: 캐시 후보의 listing_days 실전파 + s_신 축 선택 ──────────
def _prefetch_row(listing_days, h252):
    from types import SimpleNamespace

    return SimpleNamespace(h_ref_60=100.0, h_ref_252=h252, atr20=1.0,
                           avg_value_20d=1e10, d1_supply_value=5e8,
                           market="KOSPI", listing_days=listing_days)


def test_candidate_from_prefetch_uses_real_listing_days():
    from app.data.broker_adapter import _candidate_from_prefetch, PREFETCH_LISTING_DAYS

    long_c = _candidate_from_prefetch("LONG", _prefetch_row(260, 120.0), "KOSPI", 1e10, {})
    short_c = _candidate_from_prefetch("SHORT", _prefetch_row(150, None), "KOSPI", 1e10, {})
    null_c = _candidate_from_prefetch("NULL", _prefetch_row(None, None), "KOSPI", 1e10, {})
    assert long_c.listing_days == 260                   # 실이력 그대로
    assert short_c.listing_days == 150
    assert null_c.listing_days == PREFETCH_LISTING_DAYS  # 미저장 시에만 보수적 폴백


def test_candidate_listing_days_drive_s_shin_axis():
    # ≥252 이력 종목은 52주 신고가(near_252) 축을, 120<=이력<252 는 60일 축만 쓴다.
    from app.data.broker_adapter import _candidate_from_prefetch
    from app.engine.signals.breakout import s_shin

    long_c = _candidate_from_prefetch("LONG", _prefetch_row(260, 120.0), "KOSPI", 1e10, {})
    short_c = _candidate_from_prefetch("SHORT", _prefetch_row(150, None), "KOSPI", 1e10, {})
    r_long = s_shin(118.0, long_c.high_60, long_c.high_252, long_c.listing_days)
    r_short = s_shin(99.0, short_c.high_60, short_c.high_252, short_c.listing_days)
    assert r_long.near_252 is not None                  # 52주 신고가 축 복원
    assert r_long.label == "52주 신고가"
    assert r_short.near_252 is None                      # 60일 축만
    assert r_short.label == "가용구간 고가"


# ── Part B: get_quotes_bulk 병렬화(스레드풀) — 결과·커버리지 불변 ──────────
def _live_adapter_for_bulk():
    from app.data.broker_adapter import LiveBrokerDataAdapter

    class _Kis:
        def __init__(self):
            self.quotes: dict[str, Quote] = {}
            self.fail_for: set[str] = set()

        def get_quote(self, ticker):
            if ticker in self.fail_for:
                raise ConnectionError("KIS partial fail")
            return self.quotes[ticker]

    return LiveBrokerDataAdapter(
        pykrx=object(), kis=_Kis(), dart=object(),
        healthcheck_index_market=Market.KOSPI,
        healthcheck_fromdate="20250629", healthcheck_todate="20260629",
        healthcheck_expected_last="20260629")


def test_bulk_quotes_parallel_matches_serial_values():
    adapter = _live_adapter_for_bulk()
    adapter._kis.quotes = {f"T{i:02d}": Quote(f"T{i:02d}", float(i), i, 0.0)
                           for i in range(20)}
    tickers = list(adapter._kis.quotes)
    quotes, coverage = adapter.get_quotes_bulk(tickers)
    assert quotes == {t: adapter._kis.quotes[t] for t in tickers}   # 병렬=직렬 동일(순서 무관)
    assert coverage == 1.0


def test_bulk_quotes_parallel_partial_failure_coverage():
    adapter = _live_adapter_for_bulk()
    adapter._kis.quotes = {f"T{i:02d}": Quote(f"T{i:02d}", float(i), i, 0.0)
                           for i in range(10)}
    adapter._kis.fail_for = {"T03", "T07"}
    tickers = list(adapter._kis.quotes)
    quotes, coverage = adapter.get_quotes_bulk(tickers)
    assert set(quotes) == set(tickers) - {"T03", "T07"}  # 예외 종목만 조용히 스킵
    assert coverage == pytest.approx(8 / 10)


# ── Part C: get_basic_info_bulk 병렬화 — 결과 불변·빈dict/예외 종목 생략 ──────
def _live_adapter_for_info():
    from app.data.broker_adapter import LiveBrokerDataAdapter

    class _Kis:
        def __init__(self):
            self.info: dict[str, dict] = {}
            self.fail_for: set[str] = set()

        def get_stock_basic_info(self, ticker):
            if ticker in self.fail_for:
                raise ConnectionError("KIS partial fail")
            return self.info.get(ticker, {})            # 미등록 → 빈 dict(조회 실패 계약)

    return LiveBrokerDataAdapter(
        pykrx=object(), kis=_Kis(), dart=object(),
        healthcheck_index_market=Market.KOSPI,
        healthcheck_fromdate="20250629", healthcheck_todate="20260629",
        healthcheck_expected_last="20260629")


def _basic_info(ticker, *, managed=False, warning=False, preferred=False):
    return {"ticker": ticker, "name": f"N{ticker}", "is_managed": managed,
            "is_warning": warning, "is_preferred": preferred,
            "is_ineligible": bool(managed or warning or preferred)}


def test_bulk_basic_info_parallel_matches_serial():
    adapter = _live_adapter_for_info()
    adapter._kis.info = {f"T{i:02d}": _basic_info(f"T{i:02d}", preferred=(i % 2 == 0))
                         for i in range(20)}
    tickers = list(adapter._kis.info)
    info = adapter.get_basic_info_bulk(tickers)
    assert info == {t: adapter._kis.info[t] for t in tickers}   # 병렬=직렬(순서 무관)


def test_bulk_basic_info_omits_empty_and_exception():
    adapter = _live_adapter_for_info()
    adapter._kis.info = {"AAA": _basic_info("AAA", managed=True),
                         "BBB": {},                 # 조회 실패(빈 dict) → 생략
                         "CCC": _basic_info("CCC")}
    adapter._kis.fail_for = {"DDD"}                 # 예외 → 생략
    info = adapter.get_basic_info_bulk(["AAA", "BBB", "CCC", "DDD"])
    assert set(info) == {"AAA", "CCC"}              # 빈dict·예외 종목 생략
    assert info["AAA"]["is_managed"] is True


def test_bulk_basic_info_empty_input_returns_empty():
    adapter = _live_adapter_for_info()
    assert adapter.get_basic_info_bulk([]) == {}
