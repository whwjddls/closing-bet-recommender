import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PerfHeatmap from './PerfHeatmap';
import * as api from '../api/client';
import type { PerformanceResponse } from '../api/client';
import { kstToday } from '../lib/date';

const DAY_MS = 86_400_000;
// 최근 42일 창 안에 반드시 들어오도록 오늘 기준 상대 날짜로 픽스처 구성
const d = (back: number) => kstToday(Date.now() - back * DAY_MS);

const emptyAggregate: PerformanceResponse['aggregate'] = {
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
};

const withCurve: PerformanceResponse = {
  eval_date: d(0),
  picks: [],
  aggregate: {
    ...emptyAggregate,
    sample_size: 3,
    // d(2): +0.01(첫 점=증분, win) · d(1): -0.005(loss) · d(0): +0.015(win)
    cumulative_curve: [
      { date: d(2), cum: 0.01 },
      { date: d(1), cum: 0.005 },
      { date: d(0), cum: 0.02 },
    ],
  },
};

function renderHeatmap() {
  return render(
    <MemoryRouter>
      <PerfHeatmap />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.restoreAllMocks());

describe('PerfHeatmap', () => {
  it('최근 42일 잔디를 그리고 승/패 셀과 카운트를 표시한다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(withCurve);
    renderHeatmap();

    const cells = await screen.findAllByTestId('heat-cell');
    expect(cells).toHaveLength(42);
    const wins = cells.filter((c) => c.getAttribute('data-kind') === 'win');
    const losses = cells.filter((c) => c.getAttribute('data-kind') === 'loss');
    expect(wins).toHaveLength(2);
    expect(losses).toHaveLength(1);
    expect(screen.getByTestId('perf-heatmap')).toHaveTextContent(
      '성공 2 · 실패 1',
    );
  });

  it('표본 0이면 컨테이너 안에 정직한 빈 상태', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue({
      eval_date: '',
      picks: [],
      aggregate: emptyAggregate,
    });
    renderHeatmap();
    const container = await screen.findByTestId('perf-heatmap');
    expect(
      within(container).getByTestId('perf-heatmap-empty'),
    ).toHaveTextContent('아직 기록이 없어요');
  });

  it('fetch 실패해도 크래시 없이 빈 상태(컨테이너 유지)', async () => {
    vi.spyOn(api, 'fetchPerformance').mockRejectedValue(new Error('network'));
    renderHeatmap();
    const container = await screen.findByTestId('perf-heatmap');
    expect(
      within(container).getByTestId('perf-heatmap-empty'),
    ).toBeInTheDocument();
  });

  it('/performance 로 이동하는 링크다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(withCurve);
    renderHeatmap();
    const container = await screen.findByTestId('perf-heatmap');
    expect(container).toHaveAttribute('href', '/performance');
  });
});
