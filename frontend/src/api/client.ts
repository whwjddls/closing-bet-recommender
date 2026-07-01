// Response types are pinned to interface-contracts §5 (pydantic v2 정본).
// 충돌 시 이 계약이 개별 플랜 본문보다 우선한다.

export type Market = 'KOSPI' | 'KOSDAQ';
export type Grade = 'S' | 'A' | 'B' | 'C';
export type Outcome = 'SUCCESS' | 'FAIL' | 'NA';
export type HealthStatus = 'OK' | 'DEGRADED' | 'DOWN';

export interface Candle {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BaseBox {
  start: string;
  end: string;
  low: number;
  high: number;
}

// §5 RecommendationRow: score(=final), exit_label, signal fields.
// 배지는 백엔드가 직렬화하지 않는다 — lib/badges.ts deriveBadges 가 단일 산출.
export interface Recommendation {
  rank: number;
  ticker: string;
  name: string;
  market: Market;
  price_provisional: number;
  buy_price_provisional: number;
  buy_price_final: number | null;
  exit_label: string;
  target_price: number;
  stop_price: number;
  score: number;
  grade: Grade;
  near_252: number | null; // 콜드스타트(<252거래일 이력)면 null
  near_60: number | null; // 콜드스타트(60일 고가 미확보)면 null
  rvol: number | null; // 콜드스타트(<20세션 MODELED 분모)면 null
  s_shin: number;
  rvol_confirm: number;
  supply_tilt: number;
  regime_mult: number;
  veto: number;
  spark: number[];
  base_flag: boolean;
  provisional_flag: boolean;
}

// §3 RegimeInfo (orchestrator) — /recommendations envelope regimes 값.
export interface RegimeInfo {
  market: Market;
  index_level: number;
  ma5: number;
  regime_mult: number;
  cond_a: boolean;
  cond_b: boolean;
}

// §5 prose: /recommendations/{date} envelope.
export interface RecommendationsResponse {
  run_date: string;
  session_type: string | null;
  data_available: boolean;
  kis_coverage_pct: number;
  regimes: Record<string, RegimeInfo>;
  recommendations: Recommendation[];
}

export interface StockContributions {
  s_shin: number;
  rvol_confirm: number;
  supply_tilt: number;
  regime_mult: number;
  veto: number;
  core: number;
}

// 종가→익일시가 오버나잇 갭 표본 통계(표본 <20 이면 백엔드가 null 반환).
export interface OvernightGap {
  mean: number; // 평균 갭(비율, +상승/−하락)
  std: number; // 변동성 σ(비율)
  worst5pct: number; // 하위 5% 최악 갭(비율, 하방 꼬리)
  n: number; // 표본 일수
}

// §5 StockDetailResponse.
export interface StockDetailResponse {
  ticker: string;
  name: string;
  price_provisional: number;
  grade: Grade;
  final: number;
  candles: Candle[];
  high_52w: number;
  prior_high: number;
  base_box: BaseBox | null;
  contributions: StockContributions;
  overnight_gap: OvernightGap | null;
}

// GET /market — 시장폭 + 업종 히트맵.
export interface MarketBreadth {
  advancers: number;
  decliners: number;
  unchanged: number;
  new_highs: number;
  limit_ups: number;
}

export interface MarketSector {
  name: string;
  change_pct: number; // 업종 등락률(%, +상승/−하락)
}

// 투자자별 순매수(억 단위, D-1 확정). +상승빨강 매수우위 / −하락파랑 매도우위.
export interface MarketInvestors {
  foreign_net: number; // 외국인 순매수(억)
  institution_net: number; // 기관 순매수(억)
  individual_net: number; // 개인 순매수(억)
}

export interface MarketResponse {
  breadth: MarketBreadth;
  sectors: MarketSector[];
  // 백엔드가 뒤늦게 붙인 필드 — 구버전 응답 호환 위해 optional.
  investors?: MarketInvestors;
}

// GET /calendar — 거래 세션 + 다가오는 만기/배당락/휴장 일정.
export interface CalendarToday {
  date: string;
  is_trading_day: boolean;
  session_type: string; // '정규' | '조기폐장' | '휴장' 등
  close_time: string; // 'HH:MM'
}

export interface CalendarEvent {
  date: string;
  kind: string; // 'expiry' | 'ex_dividend' | 'holiday' 등(백엔드 문자열)
  label: string;
  d_day: number; // D-day (0=오늘, 양수=미래)
}

export interface CalendarResponse {
  today: CalendarToday;
  upcoming: CalendarEvent[];
}

// GET /disclosures — 최근 희석성/배당 공시.
export interface DisclosureItem {
  date: string;
  ticker: string;
  name: string;
  kind: string; // '유상증자' | 'CB' | '배당' 등
  title: string;
}

export interface DisclosuresResponse {
  items: DisclosureItem[];
}

// §5 PickResult.
export interface PickResult {
  ticker: string;
  name: string;
  grade: Grade;
  buy_price_final: number | null;
  vwap_0900_1000: number | null;
  morning_return: number | null;
  outcome: Outcome;
  dart_overnight_flag: boolean;
}

export interface GradeBucket {
  grade: Grade;
  hit_rate: number;
  n: number;
}

export interface RegimeBucket {
  regime: string;
  hit_rate: number;
  n: number;
}

export interface CurvePoint {
  date: string;
  cum: number;
}

// §5 PerformanceAggregate.
export interface PerformanceAggregate {
  sample_size: number;
  hit_rate: number;
  avg_morning_return: number;
  cumulative_curve: CurvePoint[];
  by_grade: GradeBucket[];
  by_regime: RegimeBucket[];
  cold_start: boolean;
}

// §5 PerformanceResponse.
export interface PerformanceResponse {
  eval_date: string;
  picks: PickResult[];
  aggregate: PerformanceAggregate;
}

// §1 universe_cache 행 (스캐너).
export interface UniverseRow {
  ticker: string;
  name: string;
  market: Market;
  sec_type: string;
  avg_value_20d: number;
  is_managed: boolean;
  is_warning: boolean;
  is_caution: boolean;
  eligible: boolean;
}

export interface UniverseResponse {
  as_of: string | null;
  rows: UniverseRow[];
}

// §5 HealthResponse: status 대문자, reason 필드(필수).
export interface HealthResponse {
  status: HealthStatus;
  reason: string;
  kis_coverage_pct: number;
  board_published: boolean;
  last_run_date: string | null;
}

const BASE_URL =
  (import.meta.env?.VITE_API_BASE as string | undefined) ??
  'http://localhost:8000';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`API ${path} failed: ${res.status}`);
  }
  return (await res.json()) as T;
}

export const fetchRecommendations = (date: string) =>
  getJson<RecommendationsResponse>(`/recommendations/${date}`);
export const fetchStock = (code: string) =>
  getJson<StockDetailResponse>(`/stock/${code}`);
export const fetchPerformance = () =>
  getJson<PerformanceResponse>(`/performance`);
export const fetchUniverse = () => getJson<UniverseResponse>(`/universe`);
export const fetchHealth = () => getJson<HealthResponse>(`/health`);
export const fetchMarket = () => getJson<MarketResponse>(`/market`);
export const fetchCalendar = () => getJson<CalendarResponse>(`/calendar`);
export const fetchDisclosures = () =>
  getJson<DisclosuresResponse>(`/disclosures`);
