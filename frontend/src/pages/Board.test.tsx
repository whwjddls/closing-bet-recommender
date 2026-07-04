import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Board from './Board';
import * as api from '../api/client';
import type {
  RecommendationsResponse,
  UniverseResponse,
  HealthResponse,
  RegimeInfo,
} from '../api/client';

const baseRec = (over: Partial<api.Recommendation>): api.Recommendation => ({
  rank: 1,
  ticker: '000660',
  name: 'A',
  market: 'KOSDAQ',
  price_provisional: 24500,
  buy_price_provisional: 24500,
  buy_price_final: null,
  exit_label: '매도 오전 VWAP(09–10)',
  target_price: 25000,
  stop_price: 23800,
  score: 1.12,
  grade: 'S',
  near_252: 1.02,
  near_60: 1.04,
  rvol: 2.5,
  s_shin: 1.16,
  rvol_confirm: 0.93,
  supply_tilt: 1.03,
  regime_mult: 1,
  veto: 1,
  spark: [1, 2, 3],
  base_flag: false,
  provisional_flag: true,
  ...over,
});

const regime = (over: Partial<RegimeInfo>): RegimeInfo => ({
  market: 'KOSDAQ',
  index_level: 900,
  ma5: 890,
  regime_mult: 1,
  cond_a: true,
  cond_b: true,
  ...over,
});

const health: HealthResponse = {
  status: 'OK',
  reason: '',
  kis_coverage_pct: 92,
  board_published: true,
  last_run_date: '2026-06-30',
};

const universe: UniverseResponse = {
  as_of: '2026-06-30',
  rows: [
    {
      ticker: '000660',
      name: 'A',
      market: 'KOSDAQ',
      sec_type: '보통주',
      avg_value_20d: 5e9,
      is_managed: false,
      is_warning: false,
      is_caution: false,
      eligible: true,
    },
  ],
};

function setup(recRes: RecommendationsResponse) {
  vi.spyOn(api, 'fetchRecommendations').mockResolvedValue(recRes);
  vi.spyOn(api, 'fetchUniverse').mockResolvedValue(universe);
  vi.spyOn(api, 'fetchHealth').mockResolvedValue(health);
  vi.spyOn(api, 'fetchMarket').mockResolvedValue({
    breadth: {
      advancers: 520,
      decliners: 310,
      unchanged: 40,
      new_highs: 12,
      limit_ups: 3,
    },
    sectors: [
      { name: '반도체', change_pct: 2.1 },
      { name: '2차전지', change_pct: -1.4 },
    ],
  });
  vi.spyOn(api, 'fetchHighs').mockResolvedValue({ items: [] });
  vi.spyOn(api, 'fetchNews').mockResolvedValue({ items: [] }); // 재료 배지용
  // PerfHeatmap/PerfSummaryCard가 mount 시 조회 — 표본 0 픽스처로 결정성 확보.
  vi.spyOn(api, 'fetchPerformance').mockResolvedValue({
    eval_date: '',
    picks: [],
    aggregate: {
      sample_size: 0,
      hit_rate: 0,
      avg_morning_return: 0,
      cumulative_curve: [],
      by_grade: [],
      by_regime: [],
      cold_start: true,
      mdd: 0,
      payoff_ratio: 0,
      max_consec_losses: 0,
      benchmark_curve: [],
    },
  });
}

const wrap = () =>
  render(
    <MemoryRouter>
      <Board />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.stubGlobal(
    'Notification',
    Object.assign(vi.fn(), { permission: 'denied', requestPermission: vi.fn() }),
  );
});

describe('Board', () => {
  it('추천이 있으면 RecTable과 레짐 게이지를 렌더한다', async () => {
    setup({
      run_date: '2026-06-30',
      session_type: '정규',
      data_available: true,
      kis_coverage_pct: 92,
      regimes: { KOSDAQ: regime({ market: 'KOSDAQ', regime_mult: 1 }) },
      recommendations: [baseRec({})],
    });
    wrap();
    await waitFor(() =>
      expect(screen.getAllByTestId('rec-row')).toHaveLength(1),
    );
    expect(screen.getByTestId('regime-gauge')).toBeInTheDocument();
  });

  it('레일에 오늘의 걸러내기·내 전략의 달력 패널을 렌더한다', async () => {
    setup({
      run_date: '2026-06-30',
      session_type: '정규',
      data_available: true,
      kis_coverage_pct: 92,
      regimes: { KOSDAQ: regime({ market: 'KOSDAQ', regime_mult: 1 }) },
      recommendations: [baseRec({})],
    });
    wrap();
    expect(await screen.findByTestId('funnel-panel')).toBeInTheDocument();
    expect(screen.getByTestId('perf-heatmap')).toBeInTheDocument();
  });

  it('RISK_OFF(모든 레짐 0·빈 보드)이면 배너 + 스캐너 전면 유지', async () => {
    setup({
      run_date: '2026-06-30',
      session_type: '정규',
      data_available: true,
      kis_coverage_pct: 92,
      regimes: {
        KOSPI: regime({ market: 'KOSPI', regime_mult: 0, cond_a: false, cond_b: false }),
        KOSDAQ: regime({ market: 'KOSDAQ', regime_mult: 0, cond_a: false, cond_b: false }),
      },
      recommendations: [],
    });
    wrap();
    await waitFor(() =>
      expect(screen.getByTestId('risk-off-banner')).toBeInTheDocument(),
    );
    expect(
      screen.getByText('오늘은 쉬어가는 날 — 추천 없음'),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId('scan-row').length).toBeGreaterThan(0);
  });

  it('헤더에 스캔 풀 종목 수(universe 규모) 배지를 표기한다', async () => {
    setup({
      run_date: '2026-06-30',
      session_type: '정규',
      data_available: true,
      kis_coverage_pct: 92,
      regimes: { KOSDAQ: regime({ market: 'KOSDAQ', regime_mult: 1 }) },
      recommendations: [baseRec({})],
    });
    wrap();
    const badge = await screen.findByTestId('scan-pool-badge');
    expect(badge).toHaveTextContent('스캔 풀 1종목');
  });

  it('저레짐(0.5)이면 반-리스크 캡션', async () => {
    setup({
      run_date: '2026-06-30',
      session_type: '정규',
      data_available: true,
      kis_coverage_pct: 92,
      regimes: {
        KOSDAQ: regime({ market: 'KOSDAQ', regime_mult: 0.5, cond_a: true, cond_b: false }),
      },
      recommendations: [baseRec({ regime_mult: 0.5 })],
    });
    wrap();
    await waitFor(() =>
      expect(screen.getByTestId('reduced-risk-caption')).toBeInTheDocument(),
    );
  });
});
