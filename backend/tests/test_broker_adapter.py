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
