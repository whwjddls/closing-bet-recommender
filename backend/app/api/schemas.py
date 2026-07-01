from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict  # ConfigDict는 Task 6 UniverseRow(from_attributes)가 사용

EXIT_LABEL = "익일 오전 VWAP(09:00–10:00)"


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class BaseBox(BaseModel):
    start: str
    end: str
    low: float
    high: float


class RecommendationRow(BaseModel):
    rank: int
    ticker: str
    name: str
    market: str
    price_provisional: float
    buy_price_provisional: float
    buy_price_final: float | None = None
    exit_label: str = EXIT_LABEL
    target_price: float
    stop_price: float
    score: float                        # = final
    grade: str                          # S/A/B/C (core 기준)
    near_252: float
    near_60: float
    rvol: float
    s_shin: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    spark: list[float] = []
    base_flag: bool
    provisional_flag: bool


class StockDetailResponse(BaseModel):
    ticker: str
    name: str
    price_provisional: float
    grade: str
    final: float
    candles: list[Candle] = []
    high_52w: float
    prior_high: float
    base_box: BaseBox | None = None
    contributions: dict                 # {s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}


class PickResult(BaseModel):
    ticker: str
    name: str
    grade: str
    buy_price_final: float
    vwap_0900_1000: float | None = None
    morning_return: float | None = None
    outcome: str                        # SUCCESS/FAIL/NA
    dart_overnight_flag: bool


class GradeBucket(BaseModel):
    grade: str
    hit_rate: float
    n: int


class RegimeBucket(BaseModel):
    regime: str
    hit_rate: float
    n: int


class CurvePoint(BaseModel):
    date: str
    cum: float


class PerformanceAggregate(BaseModel):
    sample_size: int
    hit_rate: float
    avg_morning_return: float
    cumulative_curve: list[CurvePoint] = []
    by_grade: list[GradeBucket] = []
    by_regime: list[RegimeBucket] = []
    cold_start: bool                    # sample_size < 30


class PerformanceResponse(BaseModel):
    eval_date: str
    picks: list[PickResult] = []
    aggregate: PerformanceAggregate


class HealthResponse(BaseModel):
    status: str                         # 'OK' | 'DEGRADED' | 'DOWN' (대문자)
    reason: str                         # 사유 (필드명 reason, detail 아님)
    kis_coverage_pct: float
    board_published: bool
    last_run_date: str | None = None


class RegimeInfo(BaseModel):            # 00 §3 RegimeInfo — 시장별 레짐(게이지)
    market: str
    index_level: float
    ma5: float
    regime_mult: float
    cond_a: bool
    cond_b: bool


class RecommendationsResponse(BaseModel):
    run_date: str
    session_type: str | None = None
    data_available: bool
    kis_coverage_pct: float
    regimes: dict[str, RegimeInfo] = {}
    recommendations: list[RecommendationRow] = []


class UniverseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    name: str
    market: str
    sec_type: str
    avg_value_20d: float
    is_managed: bool
    is_warning: bool
    is_caution: bool
    listing_days: int
    eligible: bool
    as_of: date


class UniverseResponse(BaseModel):
    as_of: date | None = None
    total: int = 0
    eligible_count: int = 0
    rows: list[UniverseRow] = []


class BacktestResponse(BaseModel):
    start: date
    end: date
    n_picks: int
    rank_ic: float | None = None
    t_stat: float | None = None
    hit_rate: float | None = None
    avg_return: float | None = None
    note: str = ""
