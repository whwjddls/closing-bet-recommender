import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import FunnelPanel from './FunnelPanel';
import type { Recommendation, RecommendationsResponse } from '../api/client';

const boardBase: RecommendationsResponse = {
  run_date: '2026-07-04',
  session_type: '정규',
  data_available: true,
  kis_coverage_pct: 90.5,
  regimes: {},
  recommendations: [],
};

const fakeRecs = (n: number) =>
  Array.from({ length: n }) as unknown as Recommendation[];

describe('FunnelPanel', () => {
  it('보드 로딩 전에는 집계 중 placeholder(플로우 없음)', () => {
    render(<FunnelPanel universeCount={null} board={null} />);
    expect(screen.getByTestId('funnel-panel')).toHaveTextContent(
      '오늘의 걸러내기',
    );
    expect(screen.queryByTestId('funnel-flow')).not.toBeInTheDocument();
  });

  it('데이터 미수신이면 후보 N → — + "데이터 없음" 사유', () => {
    render(
      <FunnelPanel
        universeCount={200}
        board={{ ...boardBase, data_available: false }}
      />,
    );
    expect(screen.getByTestId('funnel-flow')).toHaveTextContent('200');
    expect(screen.getByTestId('funnel-flow')).toHaveTextContent('—');
    expect(screen.getByTestId('funnel-reason')).toHaveTextContent('데이터 없음');
  });

  it('발행 + 추천 0건이면 "신호 통과 0 — 오늘은 관망"', () => {
    render(<FunnelPanel universeCount={200} board={boardBase} />);
    expect(screen.getByTestId('funnel-flow')).toHaveTextContent('200');
    expect(screen.getByTestId('funnel-flow')).toHaveTextContent('0');
    expect(screen.getByTestId('funnel-reason')).toHaveTextContent(
      '신호 통과 0 — 오늘은 관망',
    );
  });

  it('발행 + 추천 M건이면 후보 N → M + 커버리지', () => {
    render(
      <FunnelPanel
        universeCount={200}
        board={{ ...boardBase, recommendations: fakeRecs(3) }}
      />,
    );
    const flow = screen.getByTestId('funnel-flow');
    expect(flow).toHaveTextContent('200');
    expect(flow).toHaveTextContent('3');
    expect(screen.getByTestId('funnel-panel')).toHaveTextContent(
      '커버리지 90.5%',
    );
    expect(screen.queryByTestId('funnel-reason')).not.toBeInTheDocument();
  });

  it('후보 수를 모르면(프리페치 전) 후보 자리는 — (추측 금지)', () => {
    render(<FunnelPanel universeCount={null} board={boardBase} />);
    expect(screen.getByTestId('funnel-flow')).toHaveTextContent('—');
  });
});
