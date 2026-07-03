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
  // 15:20~15:30 KIS 예상 체결가(잠정 — 확정 종가 아님). 매수가 추정 개선용. 결측 None.
  exp_close?: number | null;
  // 당일 외인/기관 가집계 라벨(잠정 — D-1 확정 수급 아님). 예: '외인▲'. 결측 None.
  supply_today?: string | null;
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

// 종목별 최근 5거래일 투자자 순매수(외인/기관). +상승빨강 매수 / −하락파랑 매도.
// 표본 부족(신규상장 등)이면 백엔드가 null 반환 → placeholder.
export interface Supply5d {
  dates: string[]; // 최근 5거래일(오름차순)
  foreign: number[]; // 외국인 순매수(dates 와 동일 길이)
  institution: number[]; // 기관 순매수(dates 와 동일 길이)
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
  grade: Grade | null;                 // 추천 이력 없는 참고 조회(신고가 위젯 진입 등)면 null
  final: number | null;
  candles: Candle[];
  high_52w: number;
  prior_high: number;
  base_box: BaseBox | null;
  contributions: Partial<StockContributions>;  // 참고 조회면 {}
  overnight_gap: OvernightGap | null;
  supply_5d: Supply5d | null; // 최근 5일 수급(표본 부족이면 null)
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
  fail_reason: string | null; // FAIL 사유(예: '갭하락', '장중반전'). 그 외 null.
}

export interface GradeBucket {
  grade: Grade;
  hit_rate: number;
  n: number;
  ci_low: number; // 적중률 신뢰구간 하한(비율)
  ci_high: number; // 적중률 신뢰구간 상한(비율)
}

export interface RegimeBucket {
  regime: string;
  hit_rate: number;
  n: number;
  ci_low: number; // 적중률 신뢰구간 하한(비율)
  ci_high: number; // 적중률 신뢰구간 상한(비율)
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
  mdd: number; // 최대낙폭(Max Drawdown, 비율, 음수/0 이하)
  payoff_ratio: number; // 손익비(평균이익/평균손실)
  max_consec_losses: number; // 최대 연속 손실 횟수
  benchmark_curve: CurvePoint[]; // 코스피 벤치마크 누적곡선(빈 배열이면 오버레이 생략)
}

// §5 PerformanceResponse.
export interface PerformanceResponse {
  eval_date: string;
  picks: PickResult[];
  aggregate: PerformanceAggregate;
}

// GET /reminder — 어제(가장 최근) 픽들의 익일 오전 청산 관리 뷰.
// morning_vwap 이 null 이면 KIS 분봉 미연동(추정 미가능) → 정직 표기.
export interface ReminderPick {
  ticker: string;
  name: string;
  grade: Grade;
  buy_price: number | null;
  target_price: number;
  stop_price: number;
  outcome: string | null; // 'SUCCESS' | 'FAIL' | 'NA' 등 백엔드 문자열(미연동이면 null)
  morning_vwap: number | null; // 오전(09–10) VWAP 청산 기준가(미연동이면 null)
}

export interface ReminderResponse {
  picks: ReminderPick[];
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

// GET /highs — 신고가(52주) 근접 종목. 장중 KIS 조회 기반(빈 배열 가능).
export interface HighItem {
  ticker: string;
  name: string; // 백엔드 기본값 '' — 미상이면 빈 문자열
}

export interface HighsResponse {
  items: HighItem[];
}

// §5 HealthResponse: status 대문자, reason 필드(필수).
export interface HealthResponse {
  status: HealthStatus;
  reason: string;
  kis_coverage_pct: number;
  board_published: boolean;
  last_run_date: string | null;
}

// POST /run — 오늘 스캔을 지금 실행(트리거). 이미 돌고 있으면 already_running.
export type RunTriggerStatus = 'started' | 'already_running';
export interface RunTriggerResponse {
  status: RunTriggerStatus;
}

// GET /run/status — 실행 상태 폴링(3초 주기). running=false 로 떨어지면 종료.
// last_result: 'OK'(추천 발행) | 'UNPUBLISHED'(오늘은 못 만듦) 등 백엔드 문자열.
// started_at/elapsed_sec: 장시간 스캔(장전 캐시 없으면 3~10분)의 경과 표시용.
export interface RunStatusResponse {
  running: boolean;
  last_result: string | null;
  last_error: string | null;
  finished_at: string | null;
  started_at: string | null; // 현재 실행 시작 시각(ISO, 미실행이면 null)
  elapsed_sec: number | null; // 현재 실행 경과 초(미실행이면 null)
}

// POST /jobs/{prefetch|scoring} — 수동 잡 트리거(버튼용).
// rejected: 실행 조건 미충족(예: 채점은 오전 10시 이후) — reason에 사유.
export type JobTriggerStatus = 'started' | 'already_running' | 'rejected';
export interface JobTriggerResponse {
  status: JobTriggerStatus;
  reason: string | null;
}

// GET /news/{ticker} — 종목 최근 뉴스(재료 확인). 빈/실패는 정직한 placeholder.
export interface NewsItem {
  datetime: string;
  title: string;
}
export interface NewsResponse {
  items: NewsItem[];
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

async function postJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, { method: 'POST' });
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
export const fetchReminder = () => getJson<ReminderResponse>(`/reminder`);
export const fetchHighs = () => getJson<HighsResponse>(`/highs`);
export const triggerRun = () => postJson<RunTriggerResponse>(`/run`);
export const fetchRunStatus = () => getJson<RunStatusResponse>(`/run/status`);
// 수동 잡 2종 — 종목 후보 가져오기(프리페치) / 성과 채점. 상태 응답은 /run/status 와 동일 형태.
export const triggerPrefetch = () => postJson<JobTriggerResponse>(`/jobs/prefetch`);
export const fetchPrefetchStatus = () =>
  getJson<RunStatusResponse>(`/jobs/prefetch/status`);
export const triggerScoring = () => postJson<JobTriggerResponse>(`/jobs/scoring`);
export const fetchScoringStatus = () =>
  getJson<RunStatusResponse>(`/jobs/scoring/status`);
export const fetchNews = (ticker: string) =>
  getJson<NewsResponse>(`/news/${ticker}`);
