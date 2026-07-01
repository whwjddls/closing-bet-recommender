import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import StockDetail from './StockDetail';
import * as api from '../api/client';
import type { StockDetailResponse } from '../api/client';

// lightweight-charts 목 (canvas 미사용). hoist-safe 하도록 vi.hoisted 사용.
const { createChart, setData, createPriceLine } = vi.hoisted(() => {
  const setData = vi.fn();
  const createPriceLine = vi.fn();
  const candleSeries = { setData, createPriceLine };
  const addCandlestickSeries = vi.fn(() => candleSeries);
  const createChart = vi.fn(() => ({
    addCandlestickSeries,
    remove: vi.fn(),
    timeScale: () => ({ fitContent: vi.fn() }),
  }));
  return { createChart, setData, createPriceLine };
});
vi.mock('lightweight-charts', () => ({ createChart, CrosshairMode: {} }));

const detail: StockDetailResponse = {
  ticker: '000660',
  name: 'A',
  price_provisional: 24500,
  grade: 'S',
  final: 1.12,
  candles: [
    { date: '2026-06-26', open: 23000, high: 23500, low: 22800, close: 23400, volume: 100 },
    { date: '2026-06-29', open: 23400, high: 24000, low: 23200, close: 23900, volume: 120 },
  ],
  high_52w: 24000,
  prior_high: 23500,
  base_box: { start: '2026-05-01', end: '2026-06-01', low: 22000, high: 23300 },
  contributions: {
    s_shin: 1.16,
    rvol_confirm: 0.93,
    supply_tilt: 1.03,
    regime_mult: 1,
    veto: 1,
    core: 1.12,
  },
};

function renderAt(code: string) {
  return render(
    <MemoryRouter initialEntries={[`/stock/${code}`]}>
      <Routes>
        <Route path="/stock/:code" element={<StockDetail />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => vi.clearAllMocks());

describe('StockDetail', () => {
  it('일봉 setData와 52주고가선/전고점 가격선을 그린다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() => expect(setData).toHaveBeenCalled());
    expect(setData).toHaveBeenCalledWith(
      expect.arrayContaining([expect.objectContaining({ close: 23900 })]),
    );
    const lineValues = createPriceLine.mock.calls.map((c) => c[0].price);
    expect(lineValues).toContain(24000); // 52주 고가선
    expect(lineValues).toContain(23500); // 전고점
  });

  it('신호 기여도 패널과 잠정 워터마크를 표시한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() =>
      expect(screen.getByTestId('contrib-core')).toHaveTextContent('1.12'),
    );
    expect(screen.getByTestId('provisional-watermark')).toBeInTheDocument();
  });

  it('베이스 박스 정보를 표기한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() =>
      expect(screen.getByTestId('base-box')).toBeInTheDocument(),
    );
  });
});
