import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  render,
  screen,
  waitFor,
  within,
  fireEvent,
} from '@testing-library/react';
import Performance from './Performance';
import * as api from '../api/client';
import type { PerformanceResponse } from '../api/client';

beforeEach(() => {
  // 페이지의 채점 버튼이 mount 시 상태를 동기화하므로 idle 응답을 stub.
  vi.spyOn(api, 'fetchScoringStatus').mockResolvedValue({
    running: false,
    last_result: null,
    last_error: null,
    finished_at: null,
    started_at: null,
    elapsed_sec: null,
  });
});

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
      fail_reason: null,
    },
    {
      ticker: '035720',
      name: 'C',
      grade: 'B',
      buy_price_final: 8120,
      vwap_0900_1000: 8090,
      morning_return: -0.019,
      outcome: 'FAIL',
      dart_overnight_flag: false,
      fail_reason: '갭하락',
    },
  ],
  aggregate: {
    sample_size: 42,
    hit_rate: 0.58,
    avg_morning_return: 0.004,
    cold_start: false,
    mdd: -0.087,
    payoff_ratio: 1.73,
    max_consec_losses: 4,
    cumulative_curve: [
      { date: '2026-06-27', cum: 0.01 },
      { date: '2026-06-29', cum: 0.018 },
    ],
    benchmark_curve: [
      { date: '2026-06-27', cum: 0.005 },
      { date: '2026-06-29', cum: 0.009 },
    ],
    by_grade: [
      { grade: 'S', hit_rate: 0.64, n: 12, ci_low: 0.5, ci_high: 0.76 },
      { grade: 'A', hit_rate: 0.55, n: 20, ci_low: 0.2, ci_high: 0.9 },
    ],
    by_regime: [
      { regime: '1.0', hit_rate: 0.6, n: 30, ci_low: 0.48, ci_high: 0.71 },
      { regime: '0.5', hit_rate: 0.48, n: 12, ci_low: 0.25, ci_high: 0.7 },
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
    expect(screen.getAllByTestId('perf-row')).toHaveLength(2);
  });

  it('리스크 지표 줄(MDD·손익비·최대연속손실)을 보여준다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('metric-mdd')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('metric-mdd')).toHaveTextContent('-8.70%');
    expect(screen.getByTestId('metric-payoff')).toHaveTextContent('1.73');
    expect(screen.getByTestId('metric-consec-losses')).toHaveTextContent('4회');
  });

  it('등급 신뢰구간을 렌더하고, 넓은 구간은 흐리게(ci-wide) 표시한다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('by-grade-S')).toBeInTheDocument(),
    );
    // S: 50~76 (폭 26%p) → 좁음, A: 20~90 (폭 70%p) → 넓음
    const sCi = within(screen.getByTestId('by-grade-S')).getByTestId('ci');
    const aCi = within(screen.getByTestId('by-grade-A')).getByTestId('ci');
    expect(sCi).toHaveTextContent('[50%~76%]');
    expect(sCi).toHaveAttribute('data-wide', 'false');
    expect(aCi).toHaveAttribute('data-wide', 'true');
  });

  it('benchmark_curve 가 있으면 코스피 오버레이(회색 라인)를 그린다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('benchmark-line')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('cum-chart')).toHaveAttribute(
      'data-has-benchmark',
      'true',
    );
  });

  it('benchmark_curve 가 빈 배열이면 오버레이를 생략한다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue({
      ...warm,
      aggregate: { ...warm.aggregate, benchmark_curve: [] },
    });
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('cum-chart')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('benchmark-line')).toBeNull();
  });

  it('FAIL 픽에 fail_reason 배지(갭하락)를 표시한다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('fail-reason')).toBeInTheDocument(),
    );
    const badge = screen.getByTestId('fail-reason');
    expect(badge).toHaveTextContent('갭하락');
    expect(badge.className).toContain('fail-reason--gap');
  });

  it('콜드스타트(표본<30)면 누적 중 캡션 + 게이팅(회색) 적용', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(cold);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('cold-start-caption')).toBeInTheDocument(),
    );
    expect(screen.getByText(/아직 기록이 쌓이는 중/)).toBeInTheDocument();
    expect(screen.getByTestId('agg-panel')).toHaveAttribute(
      'data-cold-start',
      'true',
    );
  });

  it('상단에 성과 채점하기 버튼을 노출한다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('job-scoring-btn')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('job-scoring-btn')).toHaveTextContent(
      '성과 채점하기',
    );
  });

  it('10시 이전 채점 시도(rejected)면 사유를 경고 토스트로 보여준다', async () => {
    vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
    vi.spyOn(api, 'triggerScoring').mockResolvedValue({
      status: 'rejected',
      reason: '오전 10시 이후에 눌러주세요 — 9~10시 아침 평균가 집계가 끝나야 채점할 수 있어요',
    });
    render(<Performance />);
    await waitFor(() =>
      expect(screen.getByTestId('job-scoring-btn')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('job-scoring-btn'));
    await waitFor(() =>
      expect(screen.getByTestId('job-scoring-toast')).toHaveTextContent(
        '10시 이후',
      ),
    );
    expect(screen.getByTestId('job-scoring-toast')).toHaveAttribute(
      'data-tone',
      'warn',
    );
    expect(screen.getByTestId('job-scoring-btn')).not.toBeDisabled();
  });
});
