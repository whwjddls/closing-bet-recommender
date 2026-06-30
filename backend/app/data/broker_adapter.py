from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from app.data.mapping import Market


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
