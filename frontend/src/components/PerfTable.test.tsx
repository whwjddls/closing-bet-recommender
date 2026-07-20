import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import PerfTable from './PerfTable';
import type { PickResult } from '../api/client';

const rows: PickResult[] = [
  {
    ticker: '000660',
    name: 'A',
    grade: 'S',
    buy_price_final: 24480,
    vwap_0900_0920: 24610,
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
    vwap_0900_0920: 8090,
    morning_return: -0.0037,
    outcome: 'FAIL',
    dart_overnight_flag: true,
    fail_reason: '갭하락',
  },
  {
    ticker: '068270',
    name: 'D',
    grade: 'A',
    buy_price_final: 15000,
    vwap_0900_0920: null,
    morning_return: null,
    outcome: 'NA',
    dart_overnight_flag: false,
    fail_reason: null,
  },
  {
    ticker: '005930',
    name: 'E',
    grade: 'A',
    buy_price_final: 71000,
    vwap_0900_0920: 70800,
    morning_return: -0.0028,
    outcome: 'FAIL',
    dart_overnight_flag: false,
    fail_reason: '장중반전',
  },
];

describe('PerfTable', () => {
  it('성공/실패 행에 outcome 색상 속성을 부여한다', () => {
    render(<PerfTable rows={rows} />);
    const r = screen.getAllByTestId('perf-row');
    expect(r[0]).toHaveAttribute('data-outcome', 'SUCCESS');
    expect(r[1]).toHaveAttribute('data-outcome', 'FAIL');
  });
  it('NA 행은 수익률을 N/A로(0점 처리 금지), VWAP 잠김 표기', () => {
    render(<PerfTable rows={rows} />);
    const naRow = screen.getAllByTestId('perf-row')[2];
    expect(within(naRow).getByTestId('perf-return')).toHaveTextContent('N/A');
    expect(within(naRow).getByTestId('perf-vwap')).toHaveTextContent('잠김');
  });
  it('DART 오버나잇 재스캔 플래그가 있으면 공시 배지', () => {
    render(<PerfTable rows={rows} />);
    const flagged = screen.getAllByTestId('perf-row')[1];
    expect(within(flagged).getByTestId('dart-flag')).toHaveTextContent('공시');
    const clean = screen.getAllByTestId('perf-row')[0];
    expect(within(clean).queryByTestId('dart-flag')).toBeNull();
  });
  it('수익률 부호 포맷(+0.53% / -0.37%)', () => {
    render(<PerfTable rows={rows} />);
    expect(
      within(screen.getAllByTestId('perf-row')[0]).getByTestId('perf-return'),
    ).toHaveTextContent('+0.53%');
    expect(
      within(screen.getAllByTestId('perf-row')[1]).getByTestId('perf-return'),
    ).toHaveTextContent('-0.37%');
  });
  it('FAIL 행에 fail_reason 배지(갭하락=적색/장중반전=앰버)를 표시한다', () => {
    render(<PerfTable rows={rows} />);
    const gapRow = screen.getAllByTestId('perf-row')[1];
    const gapBadge = within(gapRow).getByTestId('fail-reason');
    expect(gapBadge).toHaveTextContent('갭하락');
    expect(gapBadge.className).toContain('fail-reason--gap');

    const reversalRow = screen.getAllByTestId('perf-row')[3];
    const reversalBadge = within(reversalRow).getByTestId('fail-reason');
    expect(reversalBadge).toHaveTextContent('장중반전');
    expect(reversalBadge.className).toContain('fail-reason--reversal');

    // SUCCESS 행에는 배지 없음
    const okRow = screen.getAllByTestId('perf-row')[0];
    expect(within(okRow).queryByTestId('fail-reason')).toBeNull();
  });

  it('빈 픽이면 안내 메시지', () => {
    render(<PerfTable rows={[]} />);
    expect(screen.getByTestId('perf-empty')).toBeInTheDocument();
  });
});
