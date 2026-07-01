import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PicksTray, {
  buildPicksCsv,
  computeDistribution,
} from './PicksTray';
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

describe('PicksTray', () => {
  it('빈 트레이면 안내 힌트', () => {
    render(<PicksTray picks={[]} onRemove={() => {}} />);
    expect(screen.getByTestId('picks-tray-empty')).toHaveTextContent(
      '행에서 담기를 눌러 픽을 모으세요',
    );
  });

  it('담은 픽 칩·개수·시장분포를 보여준다', () => {
    render(
      <PicksTray
        picks={[
          rec({ ticker: '005930', name: '삼성', market: 'KOSPI' }),
          rec({ ticker: '000660', name: '하이닉스', market: 'KOSDAQ' }),
        ]}
        onRemove={() => {}}
      />,
    );
    expect(screen.getAllByTestId('pick-chip')).toHaveLength(2);
    expect(screen.getByTestId('picks-count')).toHaveTextContent('2종목');
    expect(screen.getByTestId('picks-dist')).toHaveTextContent(
      'KOSPI 1 · KOSDAQ 1',
    );
    // 균형 잡히면 쏠림 경고 없음
    expect(
      screen.queryByTestId('picks-concentration-warning'),
    ).not.toBeInTheDocument();
  });

  it('한 시장에 80%↑ 몰리면 쏠림 경고', () => {
    render(
      <PicksTray
        picks={[
          rec({ ticker: '1', market: 'KOSPI' }),
          rec({ ticker: '2', market: 'KOSPI' }),
          rec({ ticker: '3', market: 'KOSPI' }),
          rec({ ticker: '4', market: 'KOSPI' }),
          rec({ ticker: '5', market: 'KOSDAQ' }),
        ]}
        onRemove={() => {}}
      />,
    );
    const warn = screen.getByTestId('picks-concentration-warning');
    expect(warn).toHaveTextContent('KOSPI');
    expect(warn).toHaveTextContent('80%'); // 4/5 = 80% 임계 도달
  });

  it('칩의 빼기(×) 버튼이 onRemove(ticker)를 호출한다', async () => {
    const onRemove = vi.fn();
    render(
      <PicksTray
        picks={[rec({ ticker: '005930', name: '삼성' })]}
        onRemove={onRemove}
      />,
    );
    const chip = screen.getByTestId('pick-chip');
    await userEvent.click(within(chip).getByRole('button'));
    expect(onRemove).toHaveBeenCalledWith('005930');
  });
});

describe('computeDistribution', () => {
  it('4종목 전부 KOSPI면 100% 쏠림', () => {
    const d = computeDistribution([
      rec({ ticker: '1', market: 'KOSPI' }),
      rec({ ticker: '2', market: 'KOSPI' }),
      rec({ ticker: '3', market: 'KOSPI' }),
      rec({ ticker: '4', market: 'KOSPI' }),
    ]);
    expect(d.dominant).toBe('KOSPI');
    expect(d.dominantShare).toBe(1);
    expect(d.isConcentrated).toBe(true);
  });

  it('표본 3 미만이면 쏠림 판정 안 함(오탐 방지)', () => {
    const d = computeDistribution([rec({ ticker: '1', market: 'KOSPI' })]);
    expect(d.isConcentrated).toBe(false);
  });

  it('3:1(75%)은 임계(80%) 미만이라 경고 아님', () => {
    const d = computeDistribution([
      rec({ ticker: '1', market: 'KOSPI' }),
      rec({ ticker: '2', market: 'KOSPI' }),
      rec({ ticker: '3', market: 'KOSPI' }),
      rec({ ticker: '4', market: 'KOSDAQ' }),
    ]);
    expect(d.isConcentrated).toBe(false);
  });
});

describe('buildPicksCsv', () => {
  it('헤더 + 종목/코드/등급/매수가/청산 행을 만든다', () => {
    const csv = buildPicksCsv([
      rec({
        ticker: '005930',
        name: '삼성전자',
        grade: 'A',
        buy_price_final: 71000,
        exit_label: '오전 VWAP',
      }),
    ]);
    const lines = csv.split('\n');
    expect(lines[0]).toBe('종목,코드,등급,매수가,청산');
    expect(lines[1]).toBe('삼성전자,005930,A,71000,오전 VWAP');
  });

  it('buy_price_final이 없으면 잠정가를 사용한다', () => {
    const csv = buildPicksCsv([
      rec({
        ticker: '000660',
        name: '하이닉스',
        grade: 'B',
        buy_price_final: null,
        buy_price_provisional: 24500,
      }),
    ]);
    expect(csv.split('\n')[1]).toContain('24500');
  });

  it('쉼표가 든 필드는 큰따옴표로 감싼다', () => {
    const csv = buildPicksCsv([
      rec({ name: 'A, B 코퍼', exit_label: '오전 VWAP' }),
    ]);
    expect(csv.split('\n')[1]).toContain('"A, B 코퍼"');
  });
});
