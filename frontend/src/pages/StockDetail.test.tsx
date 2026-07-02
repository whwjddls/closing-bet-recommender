import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
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
  overnight_gap: { mean: 0.003, std: 0.021, worst5pct: -0.032, n: 44 },
  supply_5d: {
    dates: ['2026-06-23', '2026-06-24', '2026-06-25', '2026-06-26', '2026-06-29'],
    foreign: [120, -45, 80, 210, -30],
    institution: [-60, 30, -15, 90, 40],
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

  it('거래대금 히스토그램을 캔들 수만큼 렌더한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() =>
      expect(screen.getByTestId('volume-histogram')).toBeInTheDocument(),
    );
    expect(screen.getAllByTestId('volume-bar')).toHaveLength(detail.candles.length);
  });

  it('5승수 막대(신·거·시황·수급·재)를 렌더한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() =>
      expect(screen.getByTestId('mult-bars')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('mult-bar-s_shin')).toHaveAttribute(
      'data-dir',
      'up',
    );
    expect(screen.getByTestId('mult-bar-rvol_confirm')).toHaveAttribute(
      'data-dir',
      'down',
    );
    expect(screen.getByTestId('mult-bar-regime_mult')).toHaveAttribute(
      'data-dir',
      'flat',
    );
  });

  it('종목별 5일 수급 막대를 외인·기관 두 줄로 렌더한다', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue(detail);
    renderAt('000660');
    await waitFor(() =>
      expect(screen.getByTestId('supply-5d')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('supply-foreign')).toBeInTheDocument();
    expect(screen.getByTestId('supply-institution')).toBeInTheDocument();
    // 외인 5일 + 기관 5일 = 10개 막대
    expect(screen.getAllByTestId('supply-bar')).toHaveLength(10);
    // 첫 외인값 +120 → 매수(up), 둘째 -45 → 매도(down)
    const bars = within(screen.getByTestId('supply-foreign')).getAllByTestId(
      'supply-bar',
    );
    expect(bars[0]).toHaveAttribute('data-dir', 'up');
    expect(bars[1]).toHaveAttribute('data-dir', 'down');
  });

  it('supply_5d 가 null 이면 "수급 데이터 없음"', async () => {
    vi.spyOn(api, 'fetchStock').mockResolvedValue({ ...detail, supply_5d: null });
    renderAt('000660');
    await waitFor(() =>
      expect(screen.getByTestId('supply-5d-empty')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('supply-5d-empty')).toHaveTextContent(
      '수급 데이터 없음',
    );
  });
});
