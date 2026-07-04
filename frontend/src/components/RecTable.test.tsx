import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import RecTable from './RecTable';
import * as api from '../api/client';
import type { Recommendation } from '../api/client';

// 재료(뉴스) 배지가 각 행 mount 시 뉴스를 조회하므로 기본 stub 제공.
beforeEach(() => {
  vi.spyOn(api, 'fetchNews').mockResolvedValue({ items: [] });
});

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
  it('전체 행을 렌더하고 청산 각주(아침 9~10시)를 보여준다', () => {
    wrap(<RecTable recommendations={recs} />);
    expect(screen.getAllByTestId('rec-row')).toHaveLength(4);
    expect(screen.getByTestId('table-footnote')).toHaveTextContent(
      '아침 9~10시',
    );
  });

  it('top3(rank<=3) 행은 강조 + 순위 마커', () => {
    wrap(<RecTable recommendations={recs} />);
    const rows = screen.getAllByTestId('rec-row');
    expect(rows[0]).toHaveAttribute('data-top3', 'true');
    expect(rows[3]).toHaveAttribute('data-top3', 'false');
    expect(
      within(rows[0]).getByTestId('row-rank-marker'),
    ).toBeInTheDocument();
    expect(screen.getAllByTestId('row-rank-marker')).toHaveLength(3);
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

  it('onTogglePick 없으면 담기 버튼 미노출(기존 사용처 무영향)', () => {
    wrap(<RecTable recommendations={recs} />);
    expect(screen.queryByTestId('pick-toggle')).not.toBeInTheDocument();
  });

  it('담기 버튼 클릭 시 onTogglePick(ticker) 호출', async () => {
    const onTogglePick = vi.fn();
    wrap(
      <RecTable
        recommendations={recs}
        pickedTickers={new Set()}
        onTogglePick={onTogglePick}
      />,
    );
    const buttons = screen.getAllByTestId('pick-toggle');
    expect(buttons).toHaveLength(4);
    await userEvent.click(buttons[0]);
    // 정렬상 첫 행은 score 최상위(A, 000660)
    expect(onTogglePick).toHaveBeenCalledWith('000660');
  });

  it('예상체결가: 값이 있으면 강조 표기 + 툴팁, null이면 —', () => {
    wrap(
      <RecTable
        recommendations={[
          rec({ ticker: '111', name: 'HasExp', exp_close: 24680 }),
          rec({ ticker: '222', name: 'NoExp', exp_close: null }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId('rec-row');
    const withExp = within(rows[0]).getByTestId('exp-close');
    expect(withExp).toHaveTextContent('24,680');
    expect(within(withExp).getByTitle('15:20 예상 체결가')).toBeInTheDocument();
    const noExp = within(rows[1]).getByTestId('exp-close');
    expect(noExp).toHaveTextContent('—');
  });

  it('수급 컬럼: supply_today 있으면 풀네임+잠정 태그, 없으면 —', () => {
    wrap(
      <RecTable
        recommendations={[
          rec({ ticker: '111', name: 'HasSup', supply_today: '외인▲기관▲' }),
          rec({ ticker: '222', name: 'NoSup', supply_today: null }),
        ]}
      />,
    );
    const rows = screen.getAllByTestId('rec-row');
    const badge = within(rows[0]).getByTestId('supply-today-badge');
    expect(badge).toHaveTextContent('외국인+ 기관+'); // 축약 금지(풀네임)
    expect(badge).toHaveTextContent('잠정');
    expect(
      within(rows[1]).queryByTestId('supply-today-badge'),
    ).not.toBeInTheDocument();
    expect(within(rows[1]).getByTestId('supply-cell')).toHaveTextContent('—');
  });

  it('이미 담은 행은 담음 상태(aria-pressed)로 표시', () => {
    wrap(
      <RecTable
        recommendations={recs}
        pickedTickers={new Set(['000660'])}
        onTogglePick={() => {}}
      />,
    );
    const rowA = screen.getAllByTestId('rec-row')[0];
    const btn = within(rowA).getByTestId('pick-toggle');
    expect(btn).toHaveAttribute('aria-pressed', 'true');
    expect(btn).toHaveTextContent('담음');
  });

  it('추천이 있으면 재료(인간 최종 필터) 확인 안내를 보여준다', () => {
    wrap(<RecTable recommendations={recs} />);
    expect(screen.getByTestId('material-hint')).toHaveTextContent('재료');
    expect(screen.getByTestId('material-hint')).toHaveTextContent(
      '숫자 필터는 재료를 판단하지 못해요',
    );
  });

  it('모든 행의 재료 컬럼에 뉴스 배지를 보여준다', async () => {
    vi.spyOn(api, 'fetchNews').mockResolvedValue({
      items: [{ datetime: '20260703 1510', title: '대규모 수주 공시' }],
    });
    wrap(<RecTable recommendations={recs} />);
    const badges = await screen.findAllByTestId('news-badge');
    expect(badges).toHaveLength(4); // 전 행
    expect(badges[0]).toHaveTextContent('뉴스 1건');
  });
});
