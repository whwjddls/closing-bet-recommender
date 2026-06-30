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
    def get_universe(self, date): return self.universe
    def get_ohlcv(self, ticker, fromdate, todate): return ("ohlcv", ticker)
    def get_net_purchases(self, fromdate, todate): return self.net
    def get_index_ohlcv(self, index_code, fromdate, todate):
        return ("index", index_code)
    def health_check(self, df, expected_last_date): return self.health


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
    def dilution_veto(self, ticker, bgn_de, end_de): return self.veto


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
