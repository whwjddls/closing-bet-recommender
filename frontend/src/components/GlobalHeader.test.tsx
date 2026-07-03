import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import GlobalHeader from './GlobalHeader';
import * as api from '../api/client';
import { kstToday } from '../lib/date';

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
  // RunScanButton mount 동기화 + 헤더 스캔 상태 칩이 함께 쓴다. 기본은 "오늘 스캔 전".
  fetchRunStatus: vi.fn(() =>
    Promise.resolve({
      running: false,
      last_result: null,
      last_error: null,
      finished_at: null,
      started_at: null,
      elapsed_sec: null,
    }),
  ),
  triggerRun: vi.fn(() => Promise.resolve({ status: 'started' })),
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
    it('아직 안 돌렸으면 "오늘 스캔 전"', async () => {
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '오늘 스캔 전',
      );
    });

    it('오늘 완료(OK)면 완료 시각 + ✓', async () => {
      vi.mocked(api.fetchRunStatus).mockResolvedValue({
        running: false,
        last_result: 'OK',
        last_error: null,
        finished_at: `${kstToday()}T14:02:00+09:00`,
        started_at: null,
        elapsed_sec: null,
      });
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '스캔 14:02 완료 ✓',
      );
    });

    it('어제 완료 기록은 "오늘 스캔 전"으로 취급한다', async () => {
      vi.mocked(api.fetchRunStatus).mockResolvedValue({
        running: false,
        last_result: 'OK',
        last_error: null,
        finished_at: '2020-01-02T15:25:00+09:00', // 과거 날짜
        started_at: null,
        elapsed_sec: null,
      });
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '오늘 스캔 전',
      );
    });

    it('실행 중이면 "스캔 진행 중"', async () => {
      vi.mocked(api.fetchRunStatus).mockResolvedValue({
        running: true,
        last_result: null,
        last_error: null,
        finished_at: null,
        started_at: `${kstToday()}T15:20:00+09:00`,
        elapsed_sec: 42,
      });
      render(<GlobalHeader />);
      expect(await screen.findByTestId('scan-status')).toHaveTextContent(
        '스캔 진행 중',
      );
    });

    it('상태 조회가 실패하면 칩을 숨긴다(가짜 정보 금지)', async () => {
      vi.mocked(api.fetchRunStatus).mockRejectedValue(new Error('down'));
      render(<GlobalHeader />);
      // mount 동기화 promise들이 처리될 때까지 flush 후에도 칩은 없어야 한다.
      await act(async () => {
        await Promise.resolve();
      });
      expect(screen.queryByTestId('scan-status')).not.toBeInTheDocument();
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
