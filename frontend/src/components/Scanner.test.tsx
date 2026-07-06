import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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
  it('유니버스 행을 종목명+코드로 렌더한다', () => {
    render(
      <Scanner
        rows={[
          row({ ticker: '000660', name: 'SK하이닉스' }),
          row({ ticker: '005930', name: '삼성전자' }),
        ]}
      />,
    );
    expect(screen.getAllByTestId('scan-row')).toHaveLength(2);
    expect(screen.getAllByTestId('scan-row')[0]).toHaveTextContent('SK하이닉스');
    expect(screen.getAllByTestId('scan-row')[0]).toHaveTextContent('000660');
  });

  it('적격 판정은 15:20 스캔에서 이뤄진다는 각주를 보여준다', () => {
    render(<Scanner rows={[row({})]} />);
    expect(screen.getByTestId('scan-note')).toHaveTextContent('15:20');
  });

  it('빈 유니버스는 "장전 프리페치 전" 안내', () => {
    render(<Scanner rows={[]} />);
    expect(screen.getByTestId('scan-empty')).toHaveTextContent('장전 프리페치 전');
  });

  it('스캔 유니버스 종목 수를 카운트한다', () => {
    render(
      <Scanner
        rows={[row({ ticker: '1' }), row({ ticker: '2' }), row({ ticker: '3' })]}
      />,
    );
    const count = screen.getByTestId('scan-count');
    expect(count).toHaveTextContent('스캔 유니버스 3종목');
  });

  it('거래대금(억)순 내림차순 정렬이 기본', () => {
    render(
      <Scanner
        rows={[
          row({ ticker: 'SMALL', name: 'S', avg_value_20d: 1e9 }),
          row({ ticker: 'BIG', name: 'B', avg_value_20d: 9e9 }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId('scan-row');
    expect(rows[0]).toHaveTextContent('B');
    expect(rows[0]).toHaveTextContent('90억');
    expect(rows[1]).toHaveTextContent('S');
  });

  it('시장순 정렬: KOSPI가 KOSDAQ보다 먼저', async () => {
    render(
      <Scanner
        rows={[
          row({ ticker: 'K1', name: 'KQ', market: 'KOSDAQ', avg_value_20d: 9e9 }),
          row({ ticker: 'K2', name: 'KP', market: 'KOSPI', avg_value_20d: 1e9 }),
        ]}
      />,
    );
    await userEvent.selectOptions(screen.getByTestId('scan-sort'), 'market');
    const rows = screen.getAllByTestId('scan-row');
    expect(rows[0]).toHaveTextContent('KP');
    expect(rows[1]).toHaveTextContent('KQ');
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
