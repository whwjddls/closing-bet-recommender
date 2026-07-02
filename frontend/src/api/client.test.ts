import { describe, it, expect, vi, afterEach } from 'vitest';
import {
  fetchRecommendations,
  fetchStock,
  fetchPerformance,
  fetchUniverse,
  fetchHealth,
  fetchHighs,
  triggerRun,
  fetchRunStatus,
  fetchNews,
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

  it('nullable 계약: session_type/as_of 가 null 이어도 그대로 통과시킨다', async () => {
    mockFetchOnce({
      run_date: '2026-06-30',
      session_type: null,
      data_available: false,
      kis_coverage_pct: 0,
      regimes: {},
      recommendations: [],
    });
    const rec = await fetchRecommendations('2026-06-30');
    expect(rec.session_type).toBeNull();

    mockFetchOnce({ as_of: null, rows: [] });
    const uni = await fetchUniverse();
    expect(uni.as_of).toBeNull();
  });

  it('GET /highs — 신고가 근접 종목 items를 반환한다', async () => {
    const fn = mockFetchOnce({
      items: [{ ticker: '000660', name: 'SK하이닉스' }],
    });
    const res = await fetchHighs();
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/highs'));
    expect(res.items).toHaveLength(1);
    expect(res.items[0].ticker).toBe('000660');
  });

  it('GET /highs — 빈 items(장중 미조회)도 그대로 통과시킨다', async () => {
    mockFetchOnce({ items: [] });
    const res = await fetchHighs();
    expect(res.items).toEqual([]);
  });

  it('비정상 응답(ok=false)은 throw 하여 UI가 fail-closed 할 수 있게 한다', async () => {
    mockFetchOnce({}, false, 503);
    await expect(fetchHealth()).rejects.toThrow(/503/);
  });

  it('POST /run — 스캔 실행을 트리거하고 status를 반환한다', async () => {
    const fn = mockFetchOnce({ status: 'started' });
    const res = await triggerRun();
    expect(fn).toHaveBeenCalledWith(
      expect.stringContaining('/run'),
      expect.objectContaining({ method: 'POST' }),
    );
    expect(res.status).toBe('started');
  });

  it('POST /run — 이미 실행 중이면 already_running', async () => {
    mockFetchOnce({ status: 'already_running' });
    const res = await triggerRun();
    expect(res.status).toBe('already_running');
  });

  it('GET /run/status — 실행 상태(running·last_result·last_error)를 반환한다', async () => {
    const fn = mockFetchOnce({
      running: false,
      last_result: 'OK',
      last_error: null,
      finished_at: '2026-07-02T06:20:00+09:00',
    });
    const res = await fetchRunStatus();
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/run/status'));
    expect(res.running).toBe(false);
    expect(res.last_result).toBe('OK');
  });

  it('GET /news/{ticker} — 종목 뉴스 items를 반환한다', async () => {
    const fn = mockFetchOnce({
      items: [{ datetime: '2026-07-02 14:05', title: '3분기 수주 공시' }],
    });
    const res = await fetchNews('000660');
    expect(fn).toHaveBeenCalledWith(expect.stringContaining('/news/000660'));
    expect(res.items).toHaveLength(1);
    expect(res.items[0].title).toBe('3분기 수주 공시');
  });

  it('GET /news/{ticker} — 빈 items도 그대로 통과시킨다', async () => {
    mockFetchOnce({ items: [] });
    const res = await fetchNews('000660');
    expect(res.items).toEqual([]);
  });
});
