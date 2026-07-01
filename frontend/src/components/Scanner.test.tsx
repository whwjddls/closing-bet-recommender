import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Scanner from './Scanner';
import type { UniverseRow } from '../api/client';

function row(p: Partial<UniverseRow>): UniverseRow {
  return {
    ticker: '000000',
    name: 'X',
    market: 'KOSPI',
    sec_type: '보통주',
    avg_value_20d: 5_000_000_000,
    is_managed: false,
    is_warning: false,
    is_caution: false,
    eligible: true,
    ...p,
  };
}

describe('Scanner', () => {
  it('유니버스 행을 렌더하고 부적격 행을 표시한다', () => {
    render(
      <Scanner
        rows={[
          row({ ticker: '000660', name: 'A' }),
          row({ ticker: '005930', name: 'B', eligible: false, is_managed: true }),
        ]}
      />,
    );
    expect(screen.getAllByTestId('scan-row')).toHaveLength(2);
    const rows = screen.getAllByTestId('scan-row');
    expect(rows[1]).toHaveAttribute('data-eligible', 'false');
  });

  it('빈 유니버스는 안내 메시지', () => {
    render(<Scanner rows={[]} />);
    expect(screen.getByTestId('scan-empty')).toBeInTheDocument();
  });

  it('as_of 를 스캔 기준일로 표기한다', () => {
    render(<Scanner rows={[row({})]} asOf="2026-06-30" />);
    expect(screen.getByTestId('scan-as-of')).toHaveTextContent(
      '스캔 기준일 2026-06-30',
    );
  });

  it('as_of 가 null 이면 - 로 폴백한다', () => {
    render(<Scanner rows={[row({})]} asOf={null} />);
    expect(screen.getByTestId('scan-as-of')).toHaveTextContent('스캔 기준일 -');
  });
});
