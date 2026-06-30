import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import RecTable from './RecTable';
import type { Recommendation } from '../api/client';

function rec(p: Partial<Recommendation>): Recommendation {
  return {
    rank: 1,
    ticker: '000000',
    name: 'X',
    market: 'KOSPI',
    price_provisional: 1000,
    buy_price_provisional: 1000,
    buy_price_final: null,
    exit_label: '익일 오전 VWAP(09:00–10:00)',
    target_price: 1100,
    stop_price: 970,
    score: 0.9,
    grade: 'S',
    badges: [],
    near_252: 1.0,
    near_60: 1.0,
    rvol: 2.5,
    s_shin: 1,
    rvol_confirm: 0.9,
    supply_tilt: 1.1,
    regime_mult: 1,
    veto: 1,
    spark: [1, 2, 3],
    base_flag: false,
    provisional_flag: true,
    ...p,
  };
}

const recs: Recommendation[] = [
  rec({
    ticker: '000660',
    name: 'A',
    market: 'KOSDAQ',
    rank: 1,
    grade: 'S',
    score: 1.12,
    supply_tilt: 1.2,
  }),
  rec({
    ticker: '005930',
    name: 'B',
    market: 'KOSPI',
    rank: 2,
    grade: 'A',
    score: 0.7,
    supply_tilt: 0.9,
  }),
  rec({
    ticker: '035720',
    name: 'C',
    market: 'KOSPI',
    rank: 3,
    grade: 'B',
    score: 0.5,
    supply_tilt: 1.0,
  }),
  rec({
    ticker: '068270',
    name: 'D',
    market: 'KOSDAQ',
    rank: 4,
    grade: 'C',
    score: 0.3,
    supply_tilt: 1.05,
    buy_price_final: 12345,
    provisional_flag: false,
  }),
];

const wrap = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

describe('RecTable', () => {
  it('전체 행을 렌더하고 청산 주 CTA(오전 VWAP)를 강조한다', () => {
    wrap(<RecTable recommendations={recs} />);
    expect(screen.getAllByTestId('rec-row')).toHaveLength(4);
    expect(screen.getAllByTestId('exit-cta')[0]).toHaveTextContent('오전 VWAP');
  });

  it('top3(rank<=3) 행은 강조 표시', () => {
    wrap(<RecTable recommendations={recs} />);
    const rows = screen.getAllByTestId('rec-row');
    expect(rows[0]).toHaveAttribute('data-top3', 'true');
    expect(rows[3]).toHaveAttribute('data-top3', 'false');
  });

  it('provisional 매수가는 워터마크(*), 확정가는 워터마크 없음', () => {
    wrap(<RecTable recommendations={recs} />);
    const rowA = screen.getAllByTestId('rec-row')[0];
    expect(within(rowA).getByTestId('buy-price')).toHaveTextContent('*');
    const rowD = screen.getAllByTestId('rec-row')[3];
    expect(within(rowD).getByTestId('buy-price')).toHaveTextContent('12,345');
    expect(within(rowD).getByTestId('buy-price')).not.toHaveTextContent('*');
  });

  it('시장 필터: KOSPI만 남긴다', async () => {
    wrap(<RecTable recommendations={recs} />);
    await userEvent.selectOptions(screen.getByTestId('filter-market'), 'KOSPI');
    const names = screen.getAllByTestId('rec-name').map((n) => n.textContent);
    expect(names).toEqual(['B', 'C']);
  });

  it('수급+ 필터: supply_tilt>1만 남긴다', async () => {
    wrap(<RecTable recommendations={recs} />);
    await userEvent.click(screen.getByTestId('filter-supply-up'));
    const names = screen.getAllByTestId('rec-name').map((n) => n.textContent);
    expect(names).toEqual(['A', 'D']);
  });

  it('정렬을 등급으로 바꾸면 S→A→B→C 순', async () => {
    const shuffled = [recs[2], recs[0], recs[3], recs[1]];
    wrap(<RecTable recommendations={shuffled} />);
    await userEvent.selectOptions(screen.getByTestId('sort-key'), 'grade');
    const grades = screen.getAllByTestId('rec-grade').map((g) => g.textContent);
    expect(grades).toEqual(['S', 'A', 'B', 'C']);
  });

  it('빈 추천이면 빈 상태 메시지', () => {
    wrap(<RecTable recommendations={[]} />);
    expect(screen.getByTestId('rec-empty')).toBeInTheDocument();
  });
});
