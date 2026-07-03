import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import RunScanButton from './RunScanButton';
import * as api from '../api/client';
import { REFETCH_EVENT } from '../lib/events';
import type { RunStatusResponse } from '../api/client';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  // 아직 도는 스캔이 남은 테스트가 있어(폴링/틱 인터벌) 발사 대신 취소해
  // act() 밖 setState 경고를 막는다.
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

const NULLS = {
  last_result: null,
  last_error: null,
  finished_at: null,
  started_at: null,
  elapsed_sec: null,
} as const;

const idle: RunStatusResponse = { running: false, ...NULLS };
const running: RunStatusResponse = { running: true, ...NULLS };

// fireEvent.click + 클릭 핸들러 내부 promise(triggerRun) + mount 동기화 flush.
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

// mount 시 /run/status 동기화 microtask flush.
async function settleMount() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe('RunScanButton', () => {
  it('클릭 전에는 실행 라벨을 보여준다', async () => {
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue(idle);
    render(<RunScanButton />);
    await settleMount();
    expect(screen.getByTestId('run-scan-btn')).toHaveTextContent(
      '지금 스캔 실행',
    );
    expect(screen.getByTestId('run-scan-btn')).not.toBeDisabled();
  });

  it('클릭하면 POST /run 후 "스캔 중"으로 비활성화되고 장시간 안내를 노출한다', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus')
      .mockResolvedValueOnce(idle) // mount
      .mockResolvedValue(running); // 폴링
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));

    expect(screen.getByTestId('run-scan-btn')).toHaveTextContent('스캔 중');
    expect(screen.getByTestId('run-scan-btn')).toBeDisabled();
    expect(screen.getByTestId('run-scan-hint')).toHaveTextContent(
      '3~10분',
    );
    expect(api.triggerRun).toHaveBeenCalledTimes(1);
  });

  it('폴링이 완료(OK)되면 성공 토스트 + refetch 이벤트 발행', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus')
      .mockResolvedValueOnce(idle) // mount
      .mockResolvedValue({
        running: false,
        last_result: 'OK',
        last_error: null,
        finished_at: '2026-07-02T06:20:00+09:00',
        started_at: null,
        elapsed_sec: null,
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
    vi.spyOn(api, 'fetchRunStatus')
      .mockResolvedValueOnce(idle)
      .mockResolvedValue({
        running: false,
        last_result: 'UNPUBLISHED',
        last_error: null,
        finished_at: '2026-07-02T06:20:00+09:00',
        started_at: null,
        elapsed_sec: null,
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
    vi.spyOn(api, 'fetchRunStatus')
      .mockResolvedValueOnce(idle)
      .mockResolvedValue(running);
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));

    expect(screen.getByTestId('run-scan-note')).toHaveTextContent(
      '이미 실행 중',
    );
    expect(screen.getByTestId('run-scan-btn')).toBeDisabled();
  });

  it('last_error가 있으면 에러 토스트를 노출한다', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    vi.spyOn(api, 'fetchRunStatus')
      .mockResolvedValueOnce(idle)
      .mockResolvedValue({
        running: false,
        last_result: null,
        last_error: 'KIS 연결 실패',
        finished_at: null,
        started_at: null,
        elapsed_sec: null,
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

  it('mount 시 이미 실행 중이면 "스캔 중" 상태와 경과 시간을 복원한다', async () => {
    vi.spyOn(api, 'fetchRunStatus').mockResolvedValue({
      running: true,
      last_result: null,
      last_error: null,
      finished_at: null,
      started_at: '2026-07-02T15:18:00+09:00',
      elapsed_sec: 125,
    });
    render(<RunScanButton />);
    await settleMount();

    const btn = screen.getByTestId('run-scan-btn');
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent('스캔 중');
    expect(btn).toHaveTextContent('2분 5초'); // elapsed_sec=125
  });

  it('스캔이 끝나면 폴링을 멈춘다(인터벌 누수 없음)', async () => {
    vi.spyOn(api, 'triggerRun').mockResolvedValue({ status: 'started' });
    const statusSpy = vi
      .spyOn(api, 'fetchRunStatus')
      .mockResolvedValueOnce(idle) // mount
      .mockResolvedValue({
        running: false,
        last_result: 'OK',
        last_error: null,
        finished_at: '2026-07-02T06:20:00+09:00',
        started_at: null,
        elapsed_sec: null,
      });
    render(<RunScanButton />);
    await click(screen.getByTestId('run-scan-btn'));
    await tick(); // 첫 폴링 → 종료

    const callsAtFinish = statusSpy.mock.calls.length;
    await tick();
    await tick();
    // 종료 후에는 더 이상 /run/status를 호출하지 않는다.
    expect(statusSpy.mock.calls.length).toBe(callsAtFinish);
  });
});
