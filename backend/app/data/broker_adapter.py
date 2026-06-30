from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.data.mapping import Market, pykrx_index_code


@dataclass(slots=True)
class Quote:
    ticker: str
    price: float
    cum_volume: int
    change_pct: float
    halted: bool = False
    overheated: bool = False


@dataclass(slots=True)
class ValueRankEntry:
    ticker: str
    value: float
    rank: int


@dataclass(slots=True)
class IndexLevel:
    market: Market
    level: float


@dataclass(slots=True)
class HealthCheckResult:
    ok: bool
    last_trading_date: str | None
    row_count: int
    reason: str = ""


class BrokerDataAdapter(ABC):
    """3소스(pykrx FINAL / KIS PROVISIONAL / DART VETO)를 흡수하는 고정 계약."""

    # ── FINAL (pykrx, 장전 prefetch) ──────────────────────────────
    @abstractmethod
    def get_universe(self, date: str) -> list[str]: ...

    @abstractmethod
    def get_ohlcv(self, ticker: str, fromdate: str, todate: str) -> Any: ...

    @abstractmethod
    def get_net_purchases(self, fromdate: str, todate: str) -> dict[str, float]: ...

    @abstractmethod
    def get_index_ohlcv(self, market: Market, fromdate: str, todate: str) -> Any: ...

    @abstractmethod
    def health_check(self) -> HealthCheckResult: ...

    # ── PROVISIONAL (KIS, 15:20 스냅샷) ───────────────────────────
    @abstractmethod
    def get_value_ranking(self, market: Market) -> list[ValueRankEntry]: ...

    @abstractmethod
    def get_index_level(self, market: Market) -> IndexLevel: ...

    @abstractmethod
    def get_quote(self, ticker: str) -> Quote: ...

    # ── VETO (DART) ───────────────────────────────────────────────
    @abstractmethod
    def get_dilution_veto(self, ticker: str, bgn_de: str, end_de: str) -> int: ...


DEFAULT_COVERAGE_THRESHOLD = 0.70


def compute_coverage(requested: int, returned: int) -> float:
    if requested <= 0:
        return 0.0
    return returned / requested


def is_publishable(coverage: float,
                   threshold: float = DEFAULT_COVERAGE_THRESHOLD) -> bool:
    return coverage >= threshold


class LiveBrokerDataAdapter(BrokerDataAdapter):
    """pykrx/KIS/DART 클라이언트 + 중앙 매핑을 합성하는 구체 어댑터."""

    def __init__(self, pykrx, kis, dart, *,
                 healthcheck_index_market: Market,
                 healthcheck_fromdate: str, healthcheck_todate: str,
                 healthcheck_expected_last: str | None):
        self._pykrx = pykrx
        self._kis = kis
        self._dart = dart
        self._hc_market = healthcheck_index_market
        self._hc_from = healthcheck_fromdate
        self._hc_to = healthcheck_todate
        self._hc_expected = healthcheck_expected_last

    # ── FINAL ─────────────────────────────────────────────
    def get_universe(self, date: str) -> list[str]:
        return self._pykrx.get_universe(date)

    def get_ohlcv(self, ticker: str, fromdate: str, todate: str):
        return self._pykrx.get_ohlcv(ticker, fromdate, todate)

    def get_net_purchases(self, fromdate: str, todate: str) -> dict[str, float]:
        return self._pykrx.get_net_purchases(fromdate, todate)

    def get_index_ohlcv(self, market: Market, fromdate: str, todate: str):
        return self._pykrx.get_index_ohlcv(
            pykrx_index_code(market), fromdate, todate)

    def health_check(self) -> HealthCheckResult:
        df = self._pykrx.get_index_ohlcv(
            pykrx_index_code(self._hc_market), self._hc_from, self._hc_to)
        return self._pykrx.health_check(df, self._hc_expected)

    # ── PROVISIONAL ───────────────────────────────────────
    def get_value_ranking(self, market: Market) -> list[ValueRankEntry]:
        return self._kis.get_value_ranking(market)

    def get_index_level(self, market: Market) -> IndexLevel:
        return self._kis.get_index_level(market)

    def get_quote(self, ticker: str) -> Quote:
        return self._kis.get_quote(ticker)

    def get_quotes_bulk(self, tickers: list[str]) -> tuple[dict[str, Quote], float]:
        """부분 실패 허용 → (성공분, 커버리지). <70%면 호출측 미발행."""
        quotes: dict[str, Quote] = {}
        for ticker in tickers:
            try:
                quotes[ticker] = self._kis.get_quote(ticker)
            except Exception:
                continue
        return quotes, compute_coverage(len(tickers), len(quotes))

    # ── VETO ──────────────────────────────────────────────
    def get_dilution_veto(self, ticker: str, bgn_de: str, end_de: str) -> int:
        return self._dart.dilution_veto(ticker, bgn_de, end_de)
