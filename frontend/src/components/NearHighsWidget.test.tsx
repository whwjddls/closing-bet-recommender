import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import type { ReactElement } from 'react';
import NearHighsWidget from './NearHighsWidget';
import * as api from '../api/client';

const wrap = (ui: ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

beforeEach(() => vi.restoreAllMocks());

describe('NearHighsWidget', () => {
  it('신고가 근접 종목을 종목 칩으로 렌더한다', async () => {
    vi.spyOn(api, 'fetchHighs').mockResolvedValue({
      items: [
        { ticker: '000660', name: 'SK하이닉스' },
        { ticker: '005930', name: '삼성전자' },
      ],
    });
    wrap(<NearHighsWidget />);

    await waitFor(() =>
      expect(screen.getAllByTestId('near-high-chip')).toHaveLength(2),
    );
    const chips = screen.getAllByTestId('near-high-chip');
    expect(chips[0]).toHaveTextContent('SK하이닉스');
    expect(chips[0]).toHaveTextContent('000660');
    // 상세로 링크
    expect(chips[0]).toHaveAttribute('href', '/stock/000660');
  });

  it('빈 응답(장중 미조회)이면 정직한 placeholder', async () => {
    vi.spyOn(api, 'fetchHighs').mockResolvedValue({ items: [] });
    wrap(<NearHighsWidget />);
    expect(await screen.findByTestId('near-highs-empty')).toHaveTextContent(
      '데이터 없음(장중 조회)',
    );
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchHighs').mockRejectedValue(new Error('network'));
    wrap(<NearHighsWidget />);
    expect(await screen.findByTestId('near-highs-empty')).toHaveTextContent(
      '데이터 없음(장중 조회)',
    );
  });
});
