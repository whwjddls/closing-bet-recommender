import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PerfSummaryCard from './PerfSummaryCard';
import * as api from '../api/client';
import type { PerformanceResponse } from '../api/client';

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

const withSamples: PerformanceResponse = {
  eval_date: '2026-07-02',
  picks: [
    {
      ticker: '000660',
      name: 'SK하이닉스',
      grade: 'S',
      buy_price_final: 24500,
      vwap_0900_1000: 25200,
      morning_return: 0.028,
      outcome: 'SUCCESS',
      dart_overnight_flag: false,
      fail_reason: null,
    },
    {
      ticker: '005930',
      name: '삼성전자',
      grade: 'A',
      buy_price_final: 71000,
      vwap_0900_1000: 70300,
      morning_return: -0.0099,
      outcome: 'FAIL',
      dart_overnight_flag: false,
      fail_reason: '갭하락',
    },
  ],
  aggregate: {
    ...emptyAggregate,
    sample_size: 12,
    hit_rate: 0.58,
    avg_morning_return: 0.011,
    cold_start: true,
  },
};

function renderCard() {
  return render(
    <MemoryRouter>
      <PerfSummaryCard />
    </MemoryRouter>,
  );
}

beforeEach(() => vi.restoreAllMocks());

describe('PerfSummaryCard', () => {
  it('성공률·평균 수익률과 최근 픽 결과(1~2줄)를 보여준다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(withSamples);
    renderCard();

    const hitrate = await screen.findByTestId('perf-summary-hitrate');
    expect(hitrate).toHaveTextContent('58%');
    expect(hitrate).toHaveTextContent('n=12');
    expect(screen.getByTestId('perf-summary-card')).toHaveTextContent(
      '+1.10%',
    ); // 평균 아침 수익률

    const picks = screen.getAllByTestId('perf-summary-pick');
    expect(picks).toHaveLength(2);
    expect(picks[0]).toHaveTextContent('SK하이닉스');
    expect(picks[0]).toHaveAttribute('data-outcome', 'SUCCESS');
    expect(picks[1]).toHaveTextContent('삼성전자');
    expect(picks[1]).toHaveAttribute('data-outcome', 'FAIL');
  });

  it('최근 픽은 최대 2줄까지만 보여준다', async () => {
    const many: PerformanceResponse = {
      ...withSamples,
      picks: [
        ...withSamples.picks,
        {
          ...withSamples.picks[0],
          ticker: '035720',
          name: '카카오',
        },
      ],
    };
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(many);
    renderCard();
    await screen.findByTestId('perf-summary-picks');
    expect(screen.getAllByTestId('perf-summary-pick')).toHaveLength(2);
  });

  it('표본이 0이면 "아직 기록이 없어요"', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue({
      eval_date: '',
      picks: [],
      aggregate: emptyAggregate,
    });
    renderCard();
    expect(await screen.findByTestId('perf-summary-empty')).toHaveTextContent(
      '아직 기록이 없어요',
    );
  });

  it('fetch 실패해도 크래시 없이 기록 없음 placeholder', async () => {
    vi.spyOn(api, 'fetchPerformance').mockRejectedValue(new Error('network'));
    renderCard();
    expect(await screen.findByTestId('perf-summary-empty')).toBeInTheDocument();
  });

  it('/performance 로 이동하는 링크다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(withSamples);
    renderCard();
    await waitFor(() =>
      expect(screen.getByTestId('perf-summary-card')).toHaveAttribute(
        'href',
        '/performance',
      ),
    );
  });
});
