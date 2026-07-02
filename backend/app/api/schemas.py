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
    near_252: float | None = None       # <252거래일 이력이면 None (콜드스타트)
    near_60: float | None = None        # 60일 고가 미확보 시 None (콜드스타트)
    rvol: float | None = None           # <20세션 MODELED 분모 미축적이면 None (콜드스타트)
    s_shin: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    exp_close: float | None = None      # KIS 예상 체결가(잠정 — 확정 종가 아님); 결측 None
    supply_today: str | None = None     # 당일 외인/기관 가집계 라벨(잠정 — D-1 확정 아님); 결측 None
    spark: list[float] = []
    base_flag: bool
    provisional_flag: bool


class OvernightGap(BaseModel):          # 종가베팅 핵심 리스크: 오버나잇 갭(open[t+1]/close[t]-1) 통계
    mean: float
    std: float                          # 모표준편차(population σ)
    worst5pct: float                    # 갭 분포 5퍼센타일(하방 꼬리)
    n: int


class Supply5d(BaseModel):              # 최근 5거래일 외인·기관 순매수 거래대금(억)
    dates: list[str]
    foreign: list[float]
    institution: list[float]


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
    overnight_gap: OvernightGap | None = None   # <20 표본이면 None(콜드스타트)
    contributions: dict                 # {s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}
    supply_5d: Supply5d | None = None   # 최근 5거래일 외인·기관 수급; 미가용 시 None


class PickResult(BaseModel):
    ticker: str
    name: str
    grade: str
    buy_price_final: float | None = None    # NA(확정종가 결측) 픽은 None (#1 콜드/결측 500 방지)
    vwap_0900_1000: float | None = None
    morning_return: float | None = None
    outcome: str                        # SUCCESS/FAIL/NA
    dart_overnight_flag: bool
    fail_reason: str | None = None      # FAIL 픽 원인(갭하락/장중반전); 비-FAIL은 None


class GradeBucket(BaseModel):
    grade: str
    hit_rate: float
    n: int
    ci_low: float = 0.0                  # hit_rate Wilson 95% 신뢰구간 하한
    ci_high: float = 0.0                 # hit_rate Wilson 95% 신뢰구간 상한


class RegimeBucket(BaseModel):
    regime: str
    hit_rate: float
    n: int
    ci_low: float = 0.0                  # hit_rate Wilson 95% 신뢰구간 하한
    ci_high: float = 0.0                 # hit_rate Wilson 95% 신뢰구간 상한


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
    mdd: float = 0.0                    # 누적곡선 최대낙폭(peak-to-trough, 양수 크기)
    payoff_ratio: float = 0.0          # 손익비 = 평균이익 / |평균손실|
    max_consec_losses: int = 0         # 최대 연속 손실일(일별 합 < 0 연속)
    benchmark_curve: list[CurvePoint] = []   # 코스피 누적수익(같은 eval 기간); 미가용 시 []


class PerformanceResponse(BaseModel):
    eval_date: str
    picks: list[PickResult] = []
    aggregate: PerformanceAggregate


class ReminderPick(BaseModel):          # S7 익일 오전 청산 리마인더 — 픽별 청산 가이드
    ticker: str
    name: str
    grade: str
    buy_price: float | None = None      # buy_price_final ?? buy_price_provisional
    target_price: float
    stop_price: float
    outcome: str | None = None          # Performance 있으면 SUCCESS/FAIL/NA, 없으면 None
    morning_vwap: float | None = None   # vwap_0900_1000; 미채점/미연동 시 None(UI "추정 미연동")


class ReminderResponse(BaseModel):
    picks: list[ReminderPick] = []


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


class Breadth(BaseModel):               # 시장 폭(등락 집계) — /market 위젯
    advancers: int
    decliners: int
    unchanged: int
    new_highs: int
    limit_ups: int


class SectorChange(BaseModel):          # 업종별 등락률 — /market 위젯
    name: str
    change_pct: float


class Investors(BaseModel):             # 투자자별 수급(D-1 순매수 거래대금, 억 단위) — /market 위젯
    foreign_net: float
    institution_net: float
    individual_net: float


class MarketResponse(BaseModel):
    breadth: Breadth
    sectors: list[SectorChange] = []
    investors: Investors


class CalEvent(BaseModel):              # 거래 캘린더 개별 이벤트 — /calendar 위젯
    date: str                           # YYYY-MM-DD
    kind: str                           # 휴장 | 조기폐장 | 만기 | 배당락
    label: str
    d_day: int                          # 오늘 기준 남은 일수


class TodayInfo(BaseModel):             # 오늘 세션 정보 — /calendar 위젯
    date: str                           # YYYY-MM-DD
    is_trading_day: bool
    session_type: str                   # 정규 | 특수
    close_time: str                     # HH:MM


class CalendarResponse(BaseModel):
    today: TodayInfo
    upcoming: list[CalEvent] = []


class Disclosure(BaseModel):            # 희석/배당 관련 DART 공시 1건 — /disclosures 위젯
    date: str                           # YYYYMMDD (rcept_dt)
    ticker: str
    name: str
    kind: str                           # 희석 | 배당
    title: str                          # 공시명(report_nm)


class DisclosuresResponse(BaseModel):
    items: list[Disclosure] = []


class UniverseRow(BaseModel):
    # 장전 유니버스 라이터가 일부 필드만 채울 수 있어 전 필드 nullable (널-500 방지).
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    name: str | None = None
    market: str | None = None
    sec_type: str | None = None
    avg_value_20d: float | None = None
    is_managed: bool | None = None
    is_warning: bool | None = None
    is_caution: bool | None = None
    listing_days: int | None = None
    eligible: bool | None = None
    as_of: date


class UniverseResponse(BaseModel):
    as_of: date | None = None
    total: int = 0
    eligible_count: int = 0
    rows: list[UniverseRow] = []


class HighItem(BaseModel):              # 신고가 근접 종목 1건 — /highs 위젯
    ticker: str
    name: str = ""


class HighsResponse(BaseModel):
    items: list[HighItem] = []


class BacktestResponse(BaseModel):
    start: date
    end: date
    n_picks: int
    rank_ic: float | None = None
    t_stat: float | None = None
    hit_rate: float | None = None
    avg_return: float | None = None
    note: str = ""
