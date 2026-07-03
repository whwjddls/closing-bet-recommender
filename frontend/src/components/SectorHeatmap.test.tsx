import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SectorHeatmap from './SectorHeatmap';
import * as api from '../api/client';
import type { MarketResponse } from '../api/client';

const market: MarketResponse = {
  breadth: {
    advancers: 520,
    decliners: 310,
    unchanged: 40,
    new_highs: 12,
    limit_ups: 3,
  },
  sectors: [
    { name: '2차전지', change_pct: -1.4 },
    { name: '반도체', change_pct: 2.1 },
    { name: '바이오', change_pct: 0.0 },
  ],
};

beforeEach(() => vi.restoreAllMocks());

describe('SectorHeatmap', () => {
  it('섹터를 등락률 방향 틴트와 함께 내림차순으로 렌더한다', async () => {
    vi.spyOn(api, 'fetchMarket').mockResolvedValue(market);
    render(<SectorHeatmap />);

    await waitFor(() =>
      expect(screen.getAllByTestId('sector-tile')).toHaveLength(3),
    );

    const tiles = screen.getAllByTestId('sector-tile');
    // 내림차순: 반도체(+2.1) → 바이오(0.0) → 2차전지(-1.4)
    expect(tiles[0]).toHaveTextContent('반도체');
    expect(tiles[0]).toHaveAttribute('data-dir', 'up');
    expect(tiles[2]).toHaveTextContent('2차전지');
    expect(tiles[2]).toHaveAttribute('data-dir', 'down');
    // 방향색 표기
    expect(tiles[0]).toHaveTextContent('+2.10%');
    expect(tiles[2]).toHaveTextContent('-1.40%');
  });

  it('시장폭(상승/하락·신고가·상한가)을 표시한다', async () => {
    vi.spyOn(api, 'fetchMarket').mockResolvedValue(market);
    render(<SectorHeatmap />);

    const breadth = await screen.findByTestId('market-breadth');
    expect(breadth).toHaveTextContent('상승 520');
    expect(breadth).toHaveTextContent('하락 310');
    expect(breadth).toHaveTextContent('신고가 12');
    expect(breadth).toHaveTextContent('상한가 3');
  });

  it('빈 섹터면 정직한 placeholder', async () => {
    vi.spyOn(api, 'fetchMarket').mockResolvedValue({
      breadth: market.breadth,
      sectors: [],
    });
    render(<SectorHeatmap />);
    expect(
      await screen.findByTestId('sector-heatmap-empty'),
    ).toHaveTextContent('시장 데이터 없음');
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchMarket').mockRejectedValue(new Error('network'));
    render(<SectorHeatmap />);
    expect(
      await screen.findByTestId('sector-heatmap-empty'),
    ).toHaveTextContent('시장 데이터 없음');
  });

  it('화면 전환(재mount) 시 재조회 없이 캐시된 지표를 즉시 보여준다', async () => {
    const spy = vi.spyOn(api, 'fetchMarket').mockResolvedValue(market);
    const { unmount } = render(<SectorHeatmap />);
    await waitFor(() =>
      expect(screen.getAllByTestId('sector-tile')).toHaveLength(3),
    );
    expect(spy).toHaveBeenCalledTimes(1);
    unmount();

    // 다른 화면 갔다 오면 위젯이 remount되지만, 신선한 캐시가 있으면
    // 네트워크 재조회 없이 직전 지표를 그대로 유지한다("지표 사라짐" 방지).
    render(<SectorHeatmap />);
    expect(await screen.findByTestId('sector-tiles')).toBeInTheDocument();
    expect(screen.getAllByTestId('sector-tile')).toHaveLength(3);
    expect(spy).toHaveBeenCalledTimes(1); // 재조회 없음(캐시 히트)
  });
});
