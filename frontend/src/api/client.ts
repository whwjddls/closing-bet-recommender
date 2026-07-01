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
