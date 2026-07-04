import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import JobButton from './JobButton';
import type { JobTriggerResponse, RunStatusResponse } from '../api/client';

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
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
const doneOk: RunStatusResponse = {
  running: false,
  last_result: 'OK',
  last_error: null,
  finished_at: '2026-07-03T08:35:00+09:00',
  started_at: null,
  elapsed_sec: null,
};

function renderJob(overrides: {
  trigger?: () => Promise<JobTriggerResponse>;
  fetchStatus?: () => Promise<RunStatusResponse>;
  onDone?: () => void;
} = {}) {
  const trigger =
    overrides.trigger ??
    vi.fn().mockResolvedValue({ status: 'started', reason: null });
  const fetchStatus =
    overrides.fetchStatus ?? vi.fn().mockResolvedValue(idle);
  render(
    <JobButton
      idleLabel="종목 후보 가져오기"
      runningLabel="가져오는 중"
      hint="5~10분 걸려요"
      trigger={trigger}
      fetchStatus={fetchStatus}
      describeResult={(s) =>
        s.last_error
          ? { tone: 'error', message: s.last_error }
          : { tone: 'ok', message: '준비 완료' }
      }
      onDone={overrides.onDone}
      testId="job-prefetch"
    />,
  );
  return { trigger, fetchStatus };
}

async function click(el: HTMLElement) {
  await act(async () => {
    fireEvent.click(el);
    await vi.advanceTimersByTimeAsync(0);
  });
}

async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(3000);
  });
}

async function settleMount() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

describe('JobButton', () => {
  it('클릭 전에는 idle 라벨을 보여준다', async () => {
    renderJob();
    await settleMount();
    expect(screen.getByTestId('job-prefetch-btn')).toHaveTextContent(
      '종목 후보 가져오기',
    );
    expect(screen.getByTestId('job-prefetch-btn')).not.toBeDisabled();
  });

  it('클릭하면 트리거 후 실행 중 상태 + 힌트를 노출한다', async () => {
    const trigger = vi
      .fn()
      .mockResolvedValue({ status: 'started', reason: null });
    const fetchStatus = vi
      .fn()
      .mockResolvedValueOnce(idle) // mount
      .mockResolvedValue(running);
    renderJob({ trigger, fetchStatus });
    await click(screen.getByTestId('job-prefetch-btn'));

    expect(trigger).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('job-prefetch-btn')).toBeDisabled();
    expect(screen.getByTestId('job-prefetch-btn')).toHaveTextContent(
      '가져오는 중',
    );
    expect(screen.getByTestId('job-prefetch-hint')).toHaveTextContent(
      '5~10분',
    );
  });

  it('rejected 트리거는 사유를 경고 토스트로 보여주고 idle로 돌아온다', async () => {
    const trigger = vi.fn().mockResolvedValue({
      status: 'rejected',
      reason: '오전 10시 이후에 눌러주세요',
    });
    renderJob({ trigger });
    await click(screen.getByTestId('job-prefetch-btn'));

    expect(screen.getByTestId('job-prefetch-toast')).toHaveAttribute(
      'data-tone',
      'warn',
    );
    expect(screen.getByTestId('job-prefetch-toast')).toHaveTextContent(
      '10시 이후',
    );
    expect(screen.getByTestId('job-prefetch-btn')).not.toBeDisabled();
  });

  it('폴링 완료 시 describeResult 토스트 + onDone 호출', async () => {
    const onDone = vi.fn();
    const fetchStatus = vi
      .fn()
      .mockResolvedValueOnce(idle) // mount
      .mockResolvedValue(doneOk);
    renderJob({ fetchStatus, onDone });
    await click(screen.getByTestId('job-prefetch-btn'));
    await tick();

    expect(screen.getByTestId('job-prefetch-toast')).toHaveTextContent(
      '준비 완료',
    );
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('job-prefetch-btn')).not.toBeDisabled();
  });

  it('mount 시 이미 실행 중이면 상태를 복원한다', async () => {
    const fetchStatus = vi.fn().mockResolvedValue({
      running: true,
      last_result: null,
      last_error: null,
      finished_at: null,
      started_at: '2026-07-03T08:30:00+09:00',
      elapsed_sec: 65,
    });
    renderJob({ fetchStatus });
    await settleMount();

    const btn = screen.getByTestId('job-prefetch-btn');
    expect(btn).toBeDisabled();
    expect(btn).toHaveTextContent('1분 5초'); // elapsed_sec=65
  });

  it('완료 후에는 폴링을 멈춘다(인터벌 누수 없음)', async () => {
    const fetchStatus = vi
      .fn()
      .mockResolvedValueOnce(idle) // mount
      .mockResolvedValue(doneOk);
    renderJob({ fetchStatus });
    await click(screen.getByTestId('job-prefetch-btn'));
    await tick(); // 첫 폴링 → 종료

    const calls = fetchStatus.mock.calls.length;
    await tick();
    await tick();
    expect(fetchStatus.mock.calls.length).toBe(calls);
  });
});
