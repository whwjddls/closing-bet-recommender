from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from app.data.mapping import Market, pykrx_index_code

if TYPE_CHECKING:                                   # 순환/무거운 임포트 방지 (런타임 지연 임포트)
    from app.engine.pipeline import LiveQuote, StaticCandidate


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
# 캐시(top200) 종목의 상장일수 프록시 — 정적위생(≥120)을 통과시키는 보수적 기본값.
PREFETCH_LISTING_DAYS = 250


def _candidate_from_prefetch(ticker: str, row, live_market: str | None,
                             live_d1_value: float | None,
                             net: "Mapping[str, float]") -> "StaticCandidate":
    """FINAL 캐시 행(FinalPrefetch)으로 StaticCandidate 구성(OHLCV 재조회 없음).

    캐시에 없는 필드(recent_closes 등)는 안전한 기본값을 쓴다. market 은 라이브 랭킹 →
    캐시 저장값 → 기본(KOSPI) 순으로 확정한다."""
    from app.engine.pipeline import StaticCandidate

    high_60 = getattr(row, "h_ref_60", None)
    high_252 = getattr(row, "h_ref_252", None)
    atr20 = getattr(row, "atr20", None) or 0.0
    avg_value_20d = getattr(row, "avg_value_20d", None) or 0.0
    d1_supply_value = getattr(row, "d1_supply_value", None)
    if d1_supply_value is None:
        d1_supply_value = float(net.get(ticker, 0.0))
    market = live_market or getattr(row, "market", None) or Market.KOSPI.value
    d1_value = live_d1_value if live_d1_value is not None else avg_value_20d
    return StaticCandidate(
        ticker=ticker, name=ticker, market=market, sec_type="COMMON",
        avg_value_20d=float(avg_value_20d), is_managed=False, is_warning=False,
        is_caution=False, listing_days=PREFETCH_LISTING_DAYS,
        high_60=float(high_60) if high_60 is not None else 0.0,
        high_252=float(high_252) if high_252 is not None else None,
        prev_high=float(high_60) if high_60 is not None else 0.0,
        atr20=float(atr20), d1_supply_value=float(d1_supply_value),
        d1_value=float(d1_value), recent_closes=())


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

    # ── 과열가드/신호 배선용 KIS 래퍼 위임(모두 graceful — 상위에서 재차 방어) ──
    def get_vi_tickers(self) -> set[str]:
        return self._kis.get_vi_tickers()

    def get_limit_up_tickers(self) -> set[str]:
        return self._kis.get_limit_up_tickers()

    def get_exp_closing_prices(self) -> dict[str, float]:
        return self._kis.get_exp_closing_prices()

    def get_provisional_flows(self) -> dict[str, str]:
        return self._kis.get_provisional_flows()

    def get_stock_basic_info(self, ticker: str) -> dict:
        return self._kis.get_stock_basic_info(ticker)

    def get_near_new_highs(self) -> "list[dict]":
        return self._kis.get_near_new_highs()

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
        # DartClient.dilution_veto(ticker, snapshot_at) 계약 — end_de(=T) 를
        # snapshot 일자로 삼아 datetime 을 전달한다(arity 정합).
        snapshot_at = datetime.strptime(end_de, "%Y%m%d")
        return self._dart.dilution_veto(ticker, snapshot_at)

    def dilution_veto(self, ticker: str, snapshot_at: datetime) -> int:
        """엔진-대면 veto — orchestrate_run 이 snapshot_at 을 그대로 전달."""
        return self._dart.dilution_veto(ticker, snapshot_at)

    # ── 엔진-대면 표면 (orchestrate_run 이 소비하는 실 파이프라인 형상) ──────
    def fetch_live(self, tickers: Sequence[str]) -> "Mapping[str, LiveQuote]":
        """KIS 벌크 시세(부분 실패 허용) → {ticker: LiveQuote}. 리스트 입력·매핑 반환."""
        from app.engine.pipeline import LiveQuote

        raw, _coverage = self.get_quotes_bulk(list(tickers))
        live: dict[str, LiveQuote] = {}
        for ticker, q in raw.items():
            live[ticker] = LiveQuote(
                p_now=float(q.price),
                cum_volume_1520=float(q.cum_volume),
                day_change_pct=float(q.change_pct),
                is_limit_up=bool(getattr(q, "is_limit_up", getattr(q, "overheated", False))),
                is_vi=bool(getattr(q, "is_vi", False)),
                is_halted=bool(getattr(q, "is_halted", getattr(q, "halted", False))),
            )
        return live

    def regime_inputs(self, market: str) -> tuple[float, list[float]]:
        """(지수레벨, [c_{t-1}..c_{t-5}] 최신순 FINAL) — compute_regime 입력.

        레짐 게이트는 하루 단위 coarse 신호라 지수 레벨·5일선을 pykrx 한 소스로 통일한다
        (KIS 지수코드/스케일 불일치로 소스 혼합 시 게이트가 불안정 → prev5[0]=최근 종가를 레벨로).
        """
        mkt = market if isinstance(market, Market) else Market(market)
        prev5 = self._prev5_index_closes(mkt)
        level = prev5[0] if prev5 else 0.0
        return float(level), prev5

    def _prev5_index_closes(self, market: Market) -> list[float]:
        from datetime import timedelta as _td

        from app.data.pykrx_client import COL_CLOSE, _yyyymmdd

        today = date.today()
        end = today - _td(days=1)                               # D-1 (룩어헤드 가드)
        start = today - _td(days=40)                            # ≥5 거래일 확보용 룩백
        df = self.get_index_ohlcv(market, _yyyymmdd(start), _yyyymmdd(end))
        closes = [float(x) for x in list(df[COL_CLOSE].tail(5))]
        return closes[::-1]                                     # 최신순 [t-1..t-5]

    def build_candidates(self, run_date: date, snapshot_at: datetime, *,
                         live_top: int = 30, prefetch: "Mapping[str, Any] | None" = None,
                         ) -> "list[StaticCandidate]":
        """풀 = prefetch(FINAL 캐시) ∪ KIS 라이브 톱30×2 로 StaticCandidate 구성.

        prefetch 에 있는 종목은 캐시 데이터로 구성해 OHLCV 재조회를 생략한다(15:20 임계경로
        보호). prefetch 에 없는 라이브-only 종목만 per-ticker OHLCV 폴백을 수행한다.

        참고: sec_type/관리·경고·주의 플래그는 현 클라이언트가 노출하지 않아 보수적
        기본값(COMMON/False)을 쓰고, listing_days 는 라이브 종목은 OHLCV 행수를,
        캐시 종목은 프록시(top200=충분 유동/이력)를 사용한다.
        """
        from app.engine.pipeline import StaticCandidate
        from app.data.pykrx_client import (
            COL_CLOSE, COL_VALUE, LOOKBACK_DAYS, _yyyymmdd,
            compute_atr20, compute_avg_value_20d, compute_h_ref,
        )
        from datetime import timedelta as _td

        prefetch = prefetch or {}
        d1 = run_date - _td(days=1)
        frm = run_date - _td(days=LOOKBACK_DAYS)
        d1_s, frm_s = _yyyymmdd(d1), _yyyymmdd(frm)
        net = self.get_net_purchases(d1_s, d1_s)                # D-1 외인+기관 순매수액

        market_of: dict[str, str] = {}
        d1_value_of: dict[str, float] = {}
        pool: list[str] = []
        for market in (Market.KOSPI, Market.KOSDAQ):
            for entry in self.get_value_ranking(market)[:live_top]:
                if entry.ticker in market_of:
                    continue
                market_of[entry.ticker] = market.value
                d1_value_of[entry.ticker] = float(entry.value)
                pool.append(entry.ticker)
        for ticker in prefetch:                                  # 캐시 유니버스 union(라이브 밖 종목 포함)
            if ticker not in market_of:
                pool.append(ticker)

        candidates: list[StaticCandidate] = []
        for ticker in pool:
            row = prefetch.get(ticker)
            if row is not None:                                 # 캐시 종목 — OHLCV 재조회 금지
                candidates.append(_candidate_from_prefetch(
                    ticker, row, market_of.get(ticker), d1_value_of.get(ticker), net))
                continue
            df = self.get_ohlcv(ticker, frm_s, d1_s)            # 라이브-only 폴백
            if df is None or len(df) == 0:
                continue
            try:
                high_60 = compute_h_ref(df, 60)
                atr20 = compute_atr20(df)
                avg_value_20d = compute_avg_value_20d(df)
            except (ValueError, KeyError):
                continue
            high_252 = compute_h_ref(df, 252) if len(df) >= 252 else None
            closes = [float(x) for x in list(df[COL_CLOSE].tail(20))]
            d1_value = d1_value_of.get(ticker) or (
                float(df[COL_VALUE].iloc[-1]) if COL_VALUE in df else 0.0)
            candidates.append(StaticCandidate(
                ticker=ticker, name=ticker, market=market_of[ticker], sec_type="COMMON",
                avg_value_20d=avg_value_20d, is_managed=False, is_warning=False,
                is_caution=False, listing_days=len(df), high_60=high_60, high_252=high_252,
                prev_high=high_60, atr20=atr20, d1_supply_value=float(net.get(ticker, 0.0)),
                d1_value=d1_value, recent_closes=tuple(closes)))
        return candidates
