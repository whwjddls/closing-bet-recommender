import { useEffect, useState } from 'react';
import { Download, Moon, Sun, Timer, TriangleAlert } from 'lucide-react';
import {
  fetchRecommendations,
  fetchRunStatus,
  fetchPrefetchStatus,
  triggerPrefetch,
  type RegimeInfo,
  type RunStatusResponse,
} from '../api/client';
import { kstToday } from '../lib/date';
import { REFETCH_EVENT, emitRefetch } from '../lib/events';
import { getStoredTheme, toggleTheme, type Theme } from '../lib/theme';
import JobButton, { type JobToast } from './JobButton';
import RunScanButton from './RunScanButton';

type Verdict = 'GO' | 'CAUTION' | 'RISK_OFF';

const VERDICT_LABEL: Record<Verdict, string> = {
  GO: 'GO (공격 1.0x)',
  CAUTION: '보수 (사이즈 절반)',
  RISK_OFF: 'RISK-OFF (스킵)',
};

// 마감 15:30 KST(= 06:30 UTC 당일)까지 남은 ms. 지나면 음수.
function msUntilClose(now: Date): number {
  const kst = new Date(now.getTime() + 9 * 3600 * 1000);
  const target = Date.UTC(
    kst.getUTCFullYear(),
    kst.getUTCMonth(),
    kst.getUTCDate(),
    6,
    30,
    0,
  );
  return target - now.getTime();
}

// 60분 미만은 MM:SS, 그 이상은 "N시간 M분"으로 사람이 읽기 쉽게.
// (기존 "894:57" 처럼 분이 3자리로 폭주하던 문제 해결)
function formatCountdown(ms: number): string {
  const total = Math.floor(Math.max(0, ms) / 1000);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (total >= 3600) return `${h}시간 ${m}분`;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// ISO 시각 → KST 'YYYY-MM-DD' / 'HH:MM' (kstToday 와 같은 오프셋 방식).
function kstDateOf(iso: string): string {
  return new Date(new Date(iso).getTime() + 9 * 3600 * 1000)
    .toISOString()
    .slice(0, 10);
}

function kstHmOf(iso: string): string {
  return new Date(new Date(iso).getTime() + 9 * 3600 * 1000)
    .toISOString()
    .slice(11, 16);
}

// 스캔 상태 칩 라벨 — 기존 "기준 HH:MM:SS · N초 전"(브라우저 수신 시각이라
// 사실상 무의미)을 대체하는 진짜 정보. 오늘 완료 여부는 KST 날짜로 판정하고,
// 발행 성공(OK)일 때만 ✓를 붙인다(UNPUBLISHED 완료를 성공처럼 안 보이게).
function scanChipLabel(status: RunStatusResponse): string {
  if (status.running) return '스캔 진행 중…';
  if (status.finished_at && kstDateOf(status.finished_at) === kstToday()) {
    const check = status.last_result === 'OK' ? ' ✓' : '';
    return `스캔 ${kstHmOf(status.finished_at)} 완료${check}`;
  }
  return '오늘 스캔 전';
}

// 15:00 KST(마감 30분 전)부터 카운트다운 강조 — "결전 시간" 시각 신호(스펙 §2.1).
const CLOSE_HOT_WINDOW_MS = 30 * 60_000;

function urgencyClass(ms: number): string {
  if (ms <= 0) return 'gh-closed';
  if (ms < 60 * 1000) return 'gh-danger'; // 1분 미만 적색 점멸
  if (ms < 5 * 60 * 1000) return 'gh-warn'; // 5분 미만 앰버
  return '';
}

// 프리페치(종목 후보 가져오기) 완료 상태 → 초보자 친화 토스트.
function prefetchToast(status: RunStatusResponse): JobToast {
  if (status.last_error) return { tone: 'error', message: status.last_error };
  if (status.last_result === 'SKIPPED')
    return { tone: 'warn', message: '오늘은 휴장일이에요' };
  if (status.last_result === 'OK')
    return { tone: 'ok', message: '종목 후보 준비 완료 — 이제 스캔이 빨라요' };
  return { tone: 'warn', message: status.last_result ?? '완료' };
}

function deriveVerdict(regimes: RegimeInfo[]): Verdict | null {
  if (regimes.length === 0) return null;
  if (regimes.every((r) => r.regime_mult === 0)) return 'RISK_OFF';
  if (regimes.every((r) => r.regime_mult >= 1)) return 'GO';
  return 'CAUTION';
}

export default function GlobalHeader() {
  const [remaining, setRemaining] = useState<number>(() =>
    msUntilClose(new Date()),
  );
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  // 오늘 스캔 실행 상태(/run/status). 조회 실패면 null → 칩 숨김(가짜 정보 금지).
  const [scanStatus, setScanStatus] = useState<RunStatusResponse | null>(null);
  // 현재 테마(문서엔 main.tsx initTheme에서 이미 적용됨 — 여기선 아이콘 상태만 추적).
  const [theme, setTheme] = useState<Theme>(() => getStoredTheme());

  // 토글: 문서/저장 반영은 toggleTheme(부수효과)이 하고, 아이콘 상태만 갱신.
  const handleToggleTheme = () => setTheme(toggleTheme(theme));

  useEffect(() => {
    const tick = () => setRemaining(msUntilClose(new Date()));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let alive = true;
    fetchRecommendations(kstToday())
      .then((board) => {
        if (!alive) return;
        setVerdict(deriveVerdict(Object.values(board.regimes)));
      })
      .catch(() => {
        /* 정직성 배너·카운트다운은 데이터 없이도 상시 노출 */
      });
    return () => {
      alive = false;
    };
  }, []);

  // 스캔 상태 칩: mount 1회 + 스캔 완료 이벤트(REFETCH_EVENT) 때 갱신 — 추가 폴링 없음.
  useEffect(() => {
    let alive = true;
    const load = () => {
      fetchRunStatus()
        .then((s) => {
          if (alive) setScanStatus(s);
        })
        .catch(() => {
          if (alive) setScanStatus(null);
        });
    };
    load();
    window.addEventListener(REFETCH_EVENT, load);
    return () => {
      alive = false;
      window.removeEventListener(REFETCH_EVENT, load);
    };
  }, []);

  return (
    <div className="global-header" data-testid="global-header" role="banner">
      <div className="gh-left">
        <span className="gh-logo">
          종가베팅
          <span className="gh-logo-mark" aria-hidden="true">
            ▮
          </span>
          콘솔
        </span>
        <span
          className={`gh-countdown ${urgencyClass(remaining)}${
            remaining > 0 && remaining <= CLOSE_HOT_WINDOW_MS
              ? ' gh-countdown--hot'
              : ''
          }`}
          data-testid="close-countdown"
          title="15:30 KST 마감까지 · 지나면 다음 거래일 15:20"
        >
          <Timer size={13} aria-hidden="true" />
          {remaining <= 0
            ? ' 장 마감 · 다음 거래일 15:20'
            : ` 마감(15:30)까지 ${formatCountdown(remaining)}`}
        </span>
        {scanStatus && (
          <span
            className="gh-scan-status"
            data-testid="scan-status"
            title="오늘 스캔 실행 상태"
          >
            {scanChipLabel(scanStatus)}
          </span>
        )}
      </div>

      <div className="gh-mid">
        {verdict && (
          <span
            className={`gh-verdict verdict-${verdict}`}
            data-testid="today-verdict"
          >
            ● 오늘: {VERDICT_LABEL[verdict]}
          </span>
        )}
      </div>

      <div className="gh-right">
        <span
          className="gh-honesty"
          data-testid="honesty-banner"
          title={
            '가격: 15:20 스캔 잠정치(확정 종가 아님)\n' +
            '수급: 어제(D-1) 확정 데이터 기준\n' +
            '증권사 미연동 — 실제 주문 실행 없음'
          }
        >
          <TriangleAlert size={13} aria-hidden="true" /> 참고용 추천 · 주문은 안
          나가요
        </span>
        <button
          type="button"
          className="gh-theme-toggle"
          data-testid="theme-toggle"
          data-theme={theme}
          onClick={handleToggleTheme}
          aria-label={
            theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'
          }
          title={theme === 'dark' ? '라이트 모드로 전환' : '다크 모드로 전환'}
        >
          {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
        </button>
        <JobButton
          idleLabel={
            <>
              <Download size={14} aria-hidden="true" /> 종목 후보 가져오기
            </>
          }
          runningLabel="가져오는 중"
          hint="5~10분 걸려요 — 매일 아침 한 번이면 충분해요"
          trigger={triggerPrefetch}
          fetchStatus={fetchPrefetchStatus}
          describeResult={prefetchToast}
          onDone={emitRefetch}
          testId="job-prefetch"
        />
        <RunScanButton />
      </div>
    </div>
  );
}
