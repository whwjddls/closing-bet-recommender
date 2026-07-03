import { useCallback, useEffect, useRef, useState } from 'react';
import type { JobTriggerResponse, RunStatusResponse } from '../api/client';

// 수동 잡 트리거 버튼(범용) — "종목 후보 가져오기"(프리페치) / "성과 채점하기"(채점).
// RunScanButton과 동일한 UX 계약: mount 시 상태 동기화(이미 실행 중이면 복원),
// 3초 폴링, 로컬 1초 경과 틱(서버 elapsed_sec에 재동기화), 종료 시 인터벌 정리.
// 트리거가 rejected(실행 조건 미충족 — 예: 채점은 10시 이후)면 사유를 경고로 보여준다.

const POLL_MS = 3000;
const TICK_MS = 1000;

type Phase = 'idle' | 'running';
type Tone = 'ok' | 'warn' | 'error';
export interface JobToast {
  tone: Tone;
  message: string;
}

interface JobButtonProps {
  idleLabel: string; // 예: '📥 종목 후보 가져오기'
  runningLabel: string; // 예: '가져오는 중'
  hint?: string; // 실행 중 보조 안내(선택)
  trigger: () => Promise<JobTriggerResponse>;
  fetchStatus: () => Promise<RunStatusResponse>;
  describeResult: (status: RunStatusResponse) => JobToast; // 완료 상태 → 토스트
  onDone?: () => void; // 완료 시 후처리(데이터 갱신 등)
  testId: string;
  variant?: 'primary' | 'secondary';
}

// "N분 M초" — 1분 미만은 "M초"만.
function formatElapsed(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m >= 1 ? `${m}분 ${sec}초` : `${sec}초`;
}

export default function JobButton({
  idleLabel,
  runningLabel,
  hint,
  trigger,
  fetchStatus,
  describeResult,
  onDone,
  testId,
  variant = 'secondary',
}: JobButtonProps) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [toast, setToast] = useState<JobToast | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  const pollRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);
  const elapsedBaseRef = useRef<{ base: number; at: number }>({
    base: 0,
    at: 0,
  });

  const stopTimers = useCallback(() => {
    if (pollRef.current !== null) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (tickRef.current !== null) {
      window.clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const syncElapsed = useCallback((status: RunStatusResponse) => {
    const base = status.elapsed_sec ?? 0;
    elapsedBaseRef.current = { base, at: Date.now() };
    setElapsedSec(base);
  }, []);

  const finish = useCallback(
    (status: RunStatusResponse) => {
      stopTimers();
      setPhase('idle');
      setToast(describeResult(status));
      onDone?.();
    },
    [stopTimers, describeResult, onDone],
  );

  const poll = useCallback(async () => {
    try {
      const status = await fetchStatus();
      if (!status.running) {
        finish(status);
        return;
      }
      syncElapsed(status);
    } catch (e) {
      stopTimers();
      setPhase('idle');
      setToast({ tone: 'error', message: `상태 확인 실패: ${String(e)}` });
    }
  }, [fetchStatus, finish, syncElapsed, stopTimers]);

  const startTimers = useCallback(() => {
    stopTimers();
    pollRef.current = window.setInterval(() => {
      void poll();
    }, POLL_MS);
    tickRef.current = window.setInterval(() => {
      const { base, at } = elapsedBaseRef.current;
      setElapsedSec(base + (Date.now() - at) / 1000);
    }, TICK_MS);
  }, [poll, stopTimers]);

  const beginRunning = useCallback(
    (status: RunStatusResponse) => {
      setPhase('running');
      syncElapsed(status);
      startTimers();
    },
    [syncElapsed, startTimers],
  );

  // mount 시 상태 동기화 — 이미 실행 중이면(다른 페이지에서 시작 등) 복원.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const status = await fetchStatus();
        if (alive && status.running) beginRunning(status);
      } catch {
        /* 미실행/오프라인 — idle 유지 */
      }
    })();
    return () => {
      alive = false;
    };
    // mount 1회만 동기화(beginRunning/fetchStatus는 안정적).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => () => stopTimers(), [stopTimers]);

  const onClick = useCallback(async () => {
    if (phase === 'running') return;
    setToast(null);
    setPhase('running');
    setElapsedSec(0);
    elapsedBaseRef.current = { base: 0, at: Date.now() };
    try {
      const res = await trigger();
      if (res.status === 'rejected') {
        // 실행 조건 미충족(예: 채점은 10시 이후) — 잡이 시작되지 않음.
        stopTimers();
        setPhase('idle');
        setToast({
          tone: 'warn',
          message: res.reason ?? '지금은 실행할 수 없어요',
        });
        return;
      }
      startTimers();
    } catch (e) {
      stopTimers();
      setPhase('idle');
      setToast({ tone: 'error', message: `실행 요청 실패: ${String(e)}` });
    }
  }, [phase, trigger, startTimers, stopTimers]);

  const running = phase === 'running';

  return (
    <div className="run-scan" data-testid={testId}>
      <button
        type="button"
        className={`run-scan-btn${
          variant === 'secondary' ? ' run-scan-btn--secondary' : ''
        }`}
        data-testid={`${testId}-btn`}
        data-running={running}
        onClick={onClick}
        disabled={running}
        aria-busy={running}
        aria-live="polite"
      >
        {running ? (
          <>
            <span className="run-scan-spinner" aria-hidden="true" />
            {runningLabel} · {formatElapsed(elapsedSec)}
          </>
        ) : (
          idleLabel
        )}
      </button>

      {running && hint && (
        <span className="run-scan-hint" data-testid={`${testId}-hint`}>
          {hint}
        </span>
      )}

      {toast && (
        <span
          className={`run-scan-toast run-scan-toast--${toast.tone}`}
          data-testid={`${testId}-toast`}
          data-tone={toast.tone}
          role="status"
        >
          {toast.message}
          <button
            type="button"
            className="run-scan-toast-x"
            aria-label="알림 닫기"
            onClick={() => setToast(null)}
          >
            ×
          </button>
        </span>
      )}
    </div>
  );
}
