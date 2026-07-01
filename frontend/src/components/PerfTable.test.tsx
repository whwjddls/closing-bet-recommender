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
    vwap_0900_1000: 24610,
    morning_return: 0.0053,
    outcome: 'SUCCESS',
    dart_overnight_flag: false,
  },
  {
    ticker: '035720',
    name: 'C',
    grade: 'B',
    buy_price_final: 8120,
    vwap_0900_1000: 8090,
    morning_return: -0.0037,
    outcome: 'FAIL',
    dart_overnight_flag: true,
  },
  {
    ticker: '068270',
    name: 'D',
    grade: 'A',
    buy_price_final: 15000,
    vwap_0900_1000: null,
    morning_return: null,
    outcome: 'NA',
    dart_overnight_flag: false,
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
  it('빈 픽이면 안내 메시지', () => {
    render(<PerfTable rows={[]} />);
    expect(screen.getByTestId('perf-empty')).toBeInTheDocument();
  });
});
