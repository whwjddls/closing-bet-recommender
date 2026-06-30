import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  fetchRecommendations,
  fetchStock,
  fetchPerformance,
  fetchUniverse,
  fetchHealth,
} from './client';

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(body),
  });
  vi.stubGlobal('fetch', fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe('api client', () => {
  it('GET /recommendations/{date} 경로로 호출하고 본문을 반환한다', async () => {
    const body = {
      run_date: '2026-06-30',
      session_type: '정규',
      data_available: true,
      kis_coverage_pct: 92,
      regimes: {},
      recommendations: [],
    };
    const fn = mockFetchOnce(body);
    const res = await fetchRecommendations('2026-06-30');
    expect(fn).toHaveBeenCalledWith(
      expect.stringContaining('/recommendations/2026-06-30'),
    );
    expect(res.run_date).toBe('2026-06-30');
  });

  it('GET /stock/{code}', async () => {
    const fn = mockFetchOnce({
      ticker: '000660',
      name: 'A',
      candles: [],
      high_52w: 1,
      prior_high: 1,
    });
    await fetchStock('000660');
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/stock/000660'));
  });

  it('GET /performance', async () => {
    const fn = mockFetchOnce({ eval_date: '2026-06-29', picks: [], aggregate: {} });
    await fetchPerformance();
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/performance'));
  });

  it('GET /universe', async () => {
    const fn = mockFetchOnce({ as_of: '2026-06-30', rows: [] });
    await fetchUniverse();
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/universe'));
  });

  it('GET /health', async () => {
    const fn = mockFetchOnce({
      status: 'OK',
      kis_coverage_pct: 92,
      board_published: true,
      last_run_date: '2026-06-30',
      reason: '',
    });
    const res = await fetchHealth();
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/health'));
    expect(res.status).toBe('OK');
  });

  it('비정상 응답(ok=false)은 throw 하여 UI가 fail-closed 할 수 있게 한다', async () => {
    mockFetchOnce({}, false, 503);
    await expect(fetchHealth()).rejects.toThrow(/503/);
  });
});
