import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import RunScanButton from './RunScanButton';
import * as api from '../api/client';
import { REFETCH_EVENT } from '../lib/events';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.runOnlyPendingTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// fireEvent.click + 클릭 핸들러 내부 promise(triggerRun) 해소까지 flush.
async function click(el: HTMLElement) {
  await act(async () => {
    fireEvent.click(el);
    await vi.advanceTimersByTimeAsync(0);
  });
}

// 폴링 1회(3초) 진행 + fetchRunStatus 해소 flush.
async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
}

describe('RunScanButton', () => {
  it('클릭 전에는 실행 라벨을 보여준다', () => {
    render(<RunScanButton />);
    expect(screen.getByTestId('run-scan-btn')).toHaveTextContent(
      '지금 스캔 실행',
    );
    expect(screen.getByTestId('run-scan-btn')).not.toBeDisabled();
  });

  it('클릭하면 POST /run 후 "스캔 중…"으로 비활성화된다', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue({
      running: true,
      last_result: null,
      last_error: null,
      finished_at: null,
    });
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));

    expect(screen.getByTestId('run-scan-btn')).toHaveTextContent('스캔 중…');
    expect(screen.getByTestId('run-scan-btn')).toBeDisabled();
    expect(api.triggerRun).toHaveBeenCalledTimes(1);
  });

  it('폴링이 완료(OK)되면 성공 토스트 + refetch 이벤트 발행', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue({
      running: false,
      last_result: 'OK',
      last_error: null,
      finished_at: '2026-07-02T06:20:00+09:00',
    });
    const refetch = vi.fn();
    window.addEventListener(REFETCH_EVENT, refetch);

    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));
    await tick();

    expect(screen.getByTestId('run-scan-toast')).toHaveTextContent(
      '추천 생성 완료',
    );
    expect(screen.getByTestId('run-scan-toast')).toHaveAttribute(
      'data-tone',
      'ok',
    );
    expect(refetch).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('run-scan-btn')).not.toBeDisabled();
    window.removeEventListener(REFETCH_EVENT, refetch);
  });

  it('UNPUBLISHED 결과면 "오늘은 추천을 만들지 못했어요" 경고 토스트', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue({
      running: false,
      last_result: 'UNPUBLISHED',
      last_error: null,
      finished_at: '2026-07-02T06:20:00+09:00',
    });
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));
    await tick();

    expect(screen.getByTestId('run-scan-toast')).toHaveTextContent(
      '오늘은 추천을 만들지 못했어요',
    );
    expect(screen.getByTestId('run-scan-toast')).toHaveAttribute(
      'data-tone',
      'warn',
    );
  });

  it('already_running 응답이면 "이미 실행 중" 안내 후 폴링 합류', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({
      status: 'already_running',
    });
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue({
      running: true,
      last_result: null,
      last_error: null,
      finished_at: null,
    });
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));

    expect(screen.getByTestId('run-scan-note')).toHaveTextContent(
      '이미 실행 중',
    );
    expect(screen.getByTestId('run-scan-btn')).toBeDisabled();
  });

  it('last_error가 있으면 에러 토스트를 노출한다', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue({
      running: false,
      last_result: null,
      last_error: 'KIS 연결 실패',
      finished_at: null,
    });
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));
    await tick();

    expect(screen.getByTestId('run-scan-toast')).toHaveAttribute(
      'data-tone',
      'error',
    );
    expect(screen.getByTestId('run-scan-toast')).toHaveTextContent(
      'KIS 연결 실패',
    );
  });
});
