import { useCallback, useEffect, useRef, useState } from 'react';
import { Play } from 'lucide-react';
import {
  triggerRun,
  fetchRunStatus,
  type RunStatusResponse,
} from '../api/client';
import { emitRefetch } from '../lib/events';

// 요구 B: GlobalHeader 우측 [▶ 지금 스캔 실행] 버튼.
// POST /run → running이면 스피너+비활성("스캔 중 · N분 M초"), /run/status 3초 폴링 →
// 끝나면 결과 토스트/배지 + 보드 refetch. already_running 도 폴링으로 합류.
//
// §1-1 장시간 실행 UX: 장전 캐시가 없으면 스캔이 3~10분 걸리는 정상 동작이라,
//   (1) mount 시 /run/status 동기화로 이미 도는 스캔을 복원하고(페이지 새로고침 대비),
//   (2) 경과 시간을 로컬 1초 틱으로 표시하며(서버 elapsed_sec에 재동기화),
//   (3) 종료 시 폴링/틱 인터벌을 확실히 정리한다(누수 금지).

const POLL_MS = 3000;
const TICK_MS = 1000;
const LONG_RUN_HINT = '장전 캐시가 없으면 3~10분 걸릴 수 있어요';

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
  if (status.last_result === 'SKIPPED') {
    return { tone: 'warn', message: '오늘은 휴장일이에요' };
  }
  // 발행 창(15:15–15:30) 밖 실행은 백엔드가 차단한다 — 그 시각 누적거래량이 '15:20
  // 스냅샷'으로 저장되면 RVOL 분모(20세션 평균)가 오염되기 때문(daily_run 가드).
  if (status.last_result === 'OUTSIDE_WINDOW') {
    return {
      tone: 'warn',
      message: '스캔은 15:15~15:30에만 실행할 수 있어요 (거래량 데이터 보호)',
    };
  }
  return { tone: 'ok', message: status.last_result ?? '스캔 완료' };
}

// "N분 M초" — 1분 미만이면 "M초"만.
function formatElapsed(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return m >= 1 ? `${m}분 ${sec}초` : `${sec}초`;
}

export default function RunScanButton() {
  const [phase, setPhase] = useState<Phase>('idle');
  const [toast, setToast] = useState<Toast | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [elapsedSec, setElapsedSec] = useState(0);

  const pollRef = useRef<number | null>(null);
  const tickRef = useRef<number | null>(null);
  // 로컬 1초 틱의 기준점: 표시 경과초 = base + (now - at)/1000.
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

  // 서버 상태의 경과초로 로컬 틱 기준을 재동기화(시계 오차 방지: 절대시각 대신 경과초 사용).
  const syncElapsed = useCallback((status: RunStatusResponse) => {
    const base = status.elapsed_sec ?? 0;
    elapsedBaseRef.current = { base, at: Date.now() };
    setElapsedSec(base);
  }, []);

  const finish = useCallback(
    (status: RunStatusResponse) => {
      stopTimers();
      setPhase('idle');
      setNote(null);
      setToast(resultToast(status));
      emitRefetch();
    },
    [stopTimers],
  );

  const poll = useCallback(async () => {
    try {
      const status = await fetchRunStatus();
      if (!status.running) {
        finish(status);
        return;
      }
      syncElapsed(status);
    } catch (e) {
      stopTimers();
      setPhase('idle');
      setNote(null);
      setToast({ tone: 'error', message: `상태 확인 실패: ${String(e)}` });
    }
  }, [finish, syncElapsed, stopTimers]);

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

  // mount 시 /run/status 동기화 — 이미 running이면 "스캔 중" 복원 + 폴링 재개.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const status = await fetchRunStatus();
        if (alive && status.running) beginRunning(status);
      } catch {
        /* 미실행/오프라인 — idle 유지 */
      }
    })();
    return () => {
      alive = false;
    };
    // beginRunning은 안정적(useCallback). mount 1회만 동기화한다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 언마운트 정리(인터벌 누수 금지).
  useEffect(() => () => stopTimers(), [stopTimers]);

  const onClick = useCallback(async () => {
    if (phase === 'running') return;
    setToast(null);
    setPhase('running');
    setElapsedSec(0);
    elapsedBaseRef.current = { base: 0, at: Date.now() };
    try {
      const res = await triggerRun();
      setNote(res.status === 'already_running' ? '이미 실행 중이에요' : null);
      startTimers();
    } catch (e) {
      stopTimers();
      setPhase('idle');
      setToast({ tone: 'error', message: `실행 요청 실패: ${String(e)}` });
    }
  }, [phase, startTimers, stopTimers]);

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
            스캔 중 · {formatElapsed(elapsedSec)}
          </>
        ) : (
          <>
            <Play size={14} aria-hidden="true" /> 지금 스캔 실행
          </>
        )}
      </button>

      {running && (
        <span className="run-scan-hint" data-testid="run-scan-hint">
          {LONG_RUN_HINT}
        </span>
      )}

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
