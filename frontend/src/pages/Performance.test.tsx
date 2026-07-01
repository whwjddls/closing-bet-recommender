import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import Performance from './Performance';
import * as api from '../api/client';
import type { PerformanceResponse } from '../api/client';

const warm: PerformanceResponse = {
  eval_date: '2026-06-29',
  picks: [
    {
      ticker: '000660',
      name: 'A',
      grade: 'S',
      buy_price_final: 24480,
      vwap_0900_1000: 24610,
      morning_return: 0.0053,
      outcome: 'SUCCESS',
      dart_overnight_flag: false,
    },
  ],
  aggregate: {
    sample_size: 42,
    hit_rate: 0.58,
    avg_morning_return: 0.004,
    cold_start: false,
    cumulative_curve: [
      { date: '2026-06-27', cum: 0.01 },
      { date: '2026-06-29', cum: 0.018 },
    ],
    by_grade: [
      { grade: 'S', hit_rate: 0.64, n: 12 },
      { grade: 'A', hit_rate: 0.55, n: 20 },
    ],
    by_regime: [
      { regime: '1.0', hit_rate: 0.6, n: 30 },
      { regime: '0.5', hit_rate: 0.48, n: 12 },
    ],
  },
};

const cold: PerformanceResponse = {
  ...warm,
  aggregate: { ...warm.aggregate, sample_size: 12, cold_start: true, hit_rate: 0.5 },
};

describe('Performance', () => {
  it('표본 충분 시 집계 적중률과 등급/레짐별 적중률을 보여준다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('agg-hit-rate')).toHaveTextContent('58%'),
    );
    expect(screen.getByTestId('by-grade-S')).toHaveTextContent('64%');
    expect(screen.getByTestId('by-regime-1.0')).toHaveTextContent('60%');
    expect(screen.getByTestId('cum-curve')).toBeInTheDocument();
    expect(screen.getAllByTestId('perf-row')).toHaveLength(1);
  });

  it('콜드스타트(표본<30)면 누적 중 캡션 + 게이팅(회색) 적용', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(cold);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('cold-start-caption')).toBeInTheDocument(),
    );
    expect(screen.getByText(/데이터 누적 중/)).toBeInTheDocument();
    expect(screen.getByTestId('agg-panel')).toHaveAttribute(
      'data-cold-start',
      'true',
    );
  });
});
