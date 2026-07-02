import { useCallback, useEffect, useRef, useState } from 'react';
import {
  triggerRun,
  fetchRunStatus,
  type RunStatusResponse,
} from '../api/client';
import { emitRefetch } from '../lib/events';

// 요구 B: GlobalHeader 우측 [▶ 지금 스캔 실행] 버튼.
// POST /run → running이면 스피너+비활성("스캔 중…"), /run/status 3초 폴링 →
// 끝나면 결과 토스트/배지 + 보드 refetch. already_running 도 폴링으로 합류.

const POLL_MS = 3000;

type Phase = 'idle' | 'running';
type Tone = 'ok' | 'warn' | 'error';
interface Toast {
  tone: Tone;
  message: string;
}

// 완료 상태 → 초보자 친화 토스트. 에러 우선, 그다음 발행 여부.
function resultToast(status: RunStatusResponse): Toast {
  if (status.last_error) {
    return { tone: 'error', message: status.last_error };
  }
  if (status.last_result === 'OK') {
    return { tone: 'ok', message: '추천 생성 완료' };
  }
  if (status.last_result === 'UNPUBLISHED') {
    return { tone: 'warn', message: '오늘은 추천을 만들지 못했어요' };
  }
  return { tone: 'ok', message: status.last_result ?? '스캔 완료' };
}

export default function RunScanButton() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [toast, setToast] = useState<Toast | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const finish = useCallback(
    (status: RunStatusResponse) => {
      stopPolling();
      setPhase('idle');
      setNote(null);
      setToast(resultToast(status));
      emitRefetch();
    },
    [stopPolling],
  );

  const poll = useCallback(async () => {
    try {
      const status = await fetchRunStatus();
      if (!status.running) finish(status);
    } catch (e) {
      stopPolling();
      setPhase('idle');
      setNote(null);
      setToast({ tone: 'error', message: `상태 확인 실패: ${String(e)}` });
    }
  }, [finish, stopPolling]);

  const startPolling = useCallback(() => {
    stopPolling();
    timerRef.current = window.setInterval(() => {
      void poll();
    }, POLL_MS);
  }, [poll, stopPolling]);

  const onClick = useCallback(async () => {
    if (phase === 'running') return;
    setToast(null);
    setPhase('running');
    try {
      const res = await triggerRun();
      setNote(
        res.status === 'already_running' ? '이미 실행 중이에요' : null,
      );
      startPolling();
    } catch (e) {
      setPhase('idle');
      setToast({ tone: 'error', message: `실행 요청 실패: ${String(e)}` });
    }
  }, [phase, startPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  const running = phase === 'running';

  return (
    <div className="run-scan" data-testid="run-scan">
      <button
        type="button"
        className="run-scan-btn"
        data-testid="run-scan-btn"
        data-running={running}
        onClick={onClick}
        disabled={running}
        aria-busy={running}
        aria-live="polite"
      >
        {running ? (
          <>
            <span className="run-scan-spinner" aria-hidden="true" />
            스캔 중…
          </>
        ) : (
          <>▶ 지금 스캔 실행</>
        )}
      </button>

      {note && (
        <span className="run-scan-note" data-testid="run-scan-note">
          {note}
        </span>
      )}

      {toast && (
        <span
          className={`run-scan-toast run-scan-toast--${toast.tone}`}
          data-testid="run-scan-toast"
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
