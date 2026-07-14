import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import GlobalHeader from './GlobalHeader';
import * as api from '../api/client';
import { kstToday } from '../lib/date';
import { REFETCH_EVENT } from '../lib/events';

vi.mock('../api/client', () => ({
  fetchRecommendations: vi.fn(() =>
    Promise.resolve({
      run_date: '2026-07-02',
      session_type: null,
      data_available: true,
      kis_coverage_pct: 100,
      regimes: {},
      recommendations: [],
    }),
  ),
  // 헤더 스캔 상태 칩 — DB의 오늘 런 기록(/run/today). 기본은 런 없음(스케줄러 대기).
  fetchRunToday: vi.fn(() =>
    Promise.resolve({
      ran: false,
      status: null,
      board_published: false,
      finished_at: null,
      reason: null,
      published_count: 0,
      funnel: null,
    }),
  ),
  // 프리페치(종목 후보 가져오기) 버튼 — 기본은 미실행.
  triggerPrefetch: vi.fn(() =>
    Promise.resolve({ status: 'started', reason: null }),
  ),
  fetchPrefetchStatus: vi.fn(() =>
    Promise.resolve({
      running: false,
      last_result: null,
      last_error: null,
      finished_at: null,
      started_at: null,
      elapsed_sec: null,
    }),
  ),
}));

// mount 시 발사되는 fetch promise들을 act 안에서 정리(act 경고 방지).
async function flushMountEffects() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('GlobalHeader', () => {
  it('데이터 없이도 마감 카운트다운과 정직성 배너를 항상 렌더한다', async () => {
    render(<GlobalHeader />);
    expect(screen.getByTestId('close-countdown')).toBeInTheDocument();
    expect(screen.getByTestId('honesty-banner')).toBeInTheDocument();
    await flushMountEffects();
  });

  it('종목 후보 가져오기(프리페치) 버튼을 노출한다', async () => {
    render(<GlobalHeader />);
    expect(screen.getByTestId('job-prefetch-btn')).toHaveTextContent(
      '종목 후보 가져오기',
    );
    await flushMountEffects();
  });

  it('카운트다운은 마감 기준(15:30)을 명시한다', async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-03T01:00:00Z')); // 10:00 KST — 마감 전
    try {
      render(<GlobalHeader />);
      expect(screen.getByTestId('close-countdown')).toHaveTextContent(
        '마감(15:30)까지',
      );
      await flushMountEffects();
    } finally {
      vi.useRealTimers();
    }
  });

  it('정직성 배너는 초보자 문구로 보여주고 전문용어 상세는 툴팁에 담는다', async () => {
    render(<GlobalHeader />);
    const banner = screen.getByTestId('honesty-banner');
    expect(banner).toHaveTextContent('참고용 추천');
    expect(banner).toHaveTextContent('주문은 안 나가요');
    // 잠정·D-1·미연동 상세는 hover 툴팁으로 이동
    expect(banner.getAttribute('title')).toContain('15:20 스캔 잠정치');
    expect(banner.getAttribute('title')).toContain('D-1');
    expect(banner.getAttribute('title')).toContain('주문 실행 없음');
    await flushMountEffects();
  });

  describe('스캔 상태 칩', () => {
    it('스케줄러가 아직 안 돌렸으면 "오늘 15:20 스캔 대기"', async () => {
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '오늘 15:20 스캔 대기',
      );
    });

    it('발행 성공이면 완료 시각 + ✓ + 종목 수 (스케줄러 런도 DB로 보인다)', async () => {
      vi.mocked(api.fetchRunToday).mockResolvedValue({
        ran: true,
        status: 'OK',
        board_published: true,
        finished_at: `${kstToday()}T15:23:00+09:00`,
        reason: 'OK',
        published_count: 12,
        funnel: null,
      });
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '스캔 15:23 완료 ✓ 12종목',
      );
    });

    it('돌았지만 추천 0종목이면 성공처럼 보이지 않게 표기한다', async () => {
      vi.mocked(api.fetchRunToday).mockResolvedValue({
        ran: true,
        status: 'OK',
        board_published: true,
        finished_at: `${kstToday()}T15:23:00+09:00`,
        reason: 'RISK_OFF',
        published_count: 0,
        funnel: null,
      });
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '추천 0종목',
      );
    });

    it('미발행이면 사유를 노출한다', async () => {
      vi.mocked(api.fetchRunToday).mockResolvedValue({
        ran: true,
        status: 'UNPUBLISHED',
        board_published: false,
        finished_at: `${kstToday()}T15:23:00+09:00`,
        reason: '커버리지 65% < 70%',
        published_count: 0,
        funnel: null,
      });
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '미발행 · 커버리지 65% < 70%',
      );
    });
  });

  describe('테마 토글', () => {
    beforeEach(() => {
      localStorage.clear();
      delete document.documentElement.dataset.theme;
    });

    it('클릭하면 라이트/다크가 전환되고 localStorage에 저장된다', async () => {
      render(<GlobalHeader />);
      const toggle = screen.getByTestId('theme-toggle');
      await flushMountEffects();

      // 기본 다크 → 클릭 시 라이트
      expect(toggle).toHaveAttribute('data-theme', 'dark');
      fireEvent.click(toggle);
      expect(document.documentElement.dataset.theme).toBe('light');
      expect(localStorage.getItem('closingbet:theme')).toBe('light');
      expect(toggle).toHaveAttribute('data-theme', 'light');

      // 다시 클릭 → 다크로 복귀
      fireEvent.click(toggle);
      expect(document.documentElement.dataset.theme).toBe('dark');
      expect(localStorage.getItem('closingbet:theme')).toBe('dark');
    });
  });
});

// 스캔은 백그라운드 스케줄러가 돌리므로 UI 는 완료를 통보받을 수 없다 → 폴링으로 감지.
describe('백그라운드 스캔 자동 감지(폴링)', () => {
  it('finished_at 이 바뀌면 보드 재조회 이벤트를 브로드캐스트한다', async () => {
    vi.mocked(api.fetchRunToday)
      .mockResolvedValueOnce({
        ran: false,
        status: null,
        board_published: false,
        finished_at: null,
        reason: null,
        published_count: 0,
        funnel: null,
      })
      .mockResolvedValue({
        ran: true,
        status: 'OK',
        board_published: true,
        finished_at: `${kstToday()}T15:23:00+09:00`,
        reason: 'OK',
        published_count: 12,
        funnel: null,
      });

    const refetch = vi.fn();
    window.addEventListener(REFETCH_EVENT, refetch);
    vi.useFakeTimers();
    render(<GlobalHeader />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(refetch).not.toHaveBeenCalled(); // 첫 로드는 기준점만 잡는다

    await act(async () => {
      vi.advanceTimersByTime(30_000); // 다음 폴링 → 스캔 완료 감지
      await Promise.resolve();
    });
    expect(refetch).toHaveBeenCalled();

    vi.useRealTimers();
    window.removeEventListener(REFETCH_EVENT, refetch);
  });

  it('변화가 없으면 재조회를 쏘지 않는다(무한 루프 방지)', async () => {
    vi.mocked(api.fetchRunToday).mockResolvedValue({
      ran: true,
      status: 'OK',
      board_published: true,
      finished_at: `${kstToday()}T15:23:00+09:00`,
      reason: 'OK',
      published_count: 12,
      funnel: null,
    });

    const refetch = vi.fn();
    window.addEventListener(REFETCH_EVENT, refetch);
    vi.useFakeTimers();
    render(<GlobalHeader />);
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(90_000); // 3회 폴링 — 값 동일
      await Promise.resolve();
    });
    expect(refetch).not.toHaveBeenCalled();

    vi.useRealTimers();
    window.removeEventListener(REFETCH_EVENT, refetch);
  });
});

