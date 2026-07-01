import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import GlobalHeader from './GlobalHeader';

vi.mock('../api/client', () => ({
  fetchRecommendations: vi.fn(() =>
    Promise.resolve({
      run_date: '2026-07-02',
      session_type: null,
      data_available: true,
      kis_coverage_pct: 100,
      regimes: {},
      recommendations: [],
    }),
  ),
}));

describe('GlobalHeader', () => {
  it('데이터 없이도 마감 카운트다운과 정직성 배너를 항상 렌더한다', () => {
    render(<GlobalHeader />);
    expect(screen.getByTestId('close-countdown')).toBeInTheDocument();
    expect(screen.getByTestId('honesty-banner')).toBeInTheDocument();
  });

  it('보드 로드 후 기준 시각 · 데이터 나이 타임스탬프를 표시한다', async () => {
    render(<GlobalHeader />);
    const ts = await screen.findByTestId('data-timestamp');
    expect(ts).toHaveTextContent('기준');
    expect(ts).toHaveTextContent('초 전');
  });
});
