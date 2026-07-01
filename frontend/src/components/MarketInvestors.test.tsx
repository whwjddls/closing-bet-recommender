import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import MarketInvestors from './MarketInvestors';
import * as api from '../api/client';
import type { MarketResponse } from '../api/client';

const baseMarket: MarketResponse = {
  breadth: {
    advancers: 500,
    decliners: 300,
    unchanged: 40,
    new_highs: 10,
    limit_ups: 2,
  },
  sectors: [],
  investors: {
    foreign_net: 3200,
    institution_net: -1450,
    individual_net: -1750,
  },
};

beforeEach(() => vi.restoreAllMocks());

describe('MarketInvestors', () => {
  it('외인/기관/개인 순매수를 방향색·화살표와 함께 렌더한다', async () => {
    vi.spyOn(api, 'fetchMarket').mockResolvedValue(baseMarket);
    render(<MarketInvestors />);

    await waitFor(() =>
      expect(screen.getAllByTestId(/^investor-\w+_net$/)).toHaveLength(3),
    );

    const foreign = screen.getByTestId('investor-foreign_net');
    expect(foreign).toHaveTextContent('외국인');
    expect(foreign).toHaveTextContent('▲');
    expect(foreign).toHaveTextContent('3,200억');
    expect(foreign).toHaveAttribute('data-dir', 'up');

    const inst = screen.getByTestId('investor-institution_net');
    expect(inst).toHaveTextContent('▼');
    expect(inst).toHaveTextContent('1,450억');
    expect(inst).toHaveAttribute('data-dir', 'down');
  });

  it('investors 필드가 없으면 정직한 placeholder', async () => {
    vi.spyOn(api, 'fetchMarket').mockResolvedValue({
      breadth: baseMarket.breadth,
      sectors: [],
    });
    render(<MarketInvestors />);
    expect(
      await screen.findByTestId('market-investors-empty'),
    ).toHaveTextContent('수급 데이터 없음');
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchMarket').mockRejectedValue(new Error('network'));
    render(<MarketInvestors />);
    expect(
      await screen.findByTestId('market-investors-empty'),
    ).toHaveTextContent('수급 데이터 없음');
  });
});
