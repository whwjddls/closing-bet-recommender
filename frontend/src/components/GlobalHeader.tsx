import { useEffect, useRef, useState } from 'react';
import { Download, Moon, Sun, Timer, TriangleAlert } from 'lucide-react';
import {
  fetchRecommendations,
  fetchRunToday,
  fetchPrefetchStatus,
  fetchPrefetchToday,
  triggerPrefetch,
  type PrefetchTodayResponse,
  type RegimeInfo,
  type RunStatusResponse,
  type RunTodayResponse,
} from '../api/client';
import { kstToday } from '../lib/date';
import { REFETCH_EVENT, emitRefetch } from '../lib/events';
import { getStoredTheme, toggleTheme, type Theme } from '../lib/theme';
import JobButton, { type JobToast } from './JobButton';

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

// ISO 시각 → KST 'HH:MM' (kstToday 와 같은 오프셋 방식).
function kstHmOf(iso: string): string {
  return new Date(new Date(iso).getTime() + 9 * 3600 * 1000)
    .toISOString()
    .slice(11, 16);
}

// 스캔 상태 칩 라벨 — DB의 오늘 런 기록(/run/today) 기반이라 작업스케줄러가
// 별도 프로세스로 돌린 15:20 런도 그대로 보인다. 발행 성공일 때만 ✓·종목 수를 붙이고,
// 빈 보드/미발행은 사유를 노출한다(성공처럼 보이지 않게).
function scanChipLabel(run: RunTodayResponse): string {
  if (!run.ran) return '오늘 15:20 스캔 대기';
  const at = run.finished_at ? kstHmOf(run.finished_at) : '';
  if (run.board_published && run.published_count > 0) {
    return `스캔 ${at} 완료 ✓ ${run.published_count}종목`;
  }
  if (run.board_published) return `스캔 ${at} 완료 · 추천 0종목`;
  return `스캔 ${at} 미발행${run.reason ? ` · ${run.reason}` : ''}`;
}

// 프리스캔(장전 프리페치) 상태 칩 — DB의 오늘 산출물(/prefetch/today) 기반이라
// 08:30 스케줄러가 별도 프로세스로 돌린 실행도 그대로 보인다. 안 돌았으면 '미실행'을
// 명시해 "오늘 프리스캔 했나?" 를 UI에서 바로 알 수 있게 한다.
function prefetchChipLabel(p: PrefetchTodayResponse): string {
  if (!p.ran) return '프리스캔 미실행';
  return `프리스캔 완료 ✓ ${p.universe_count || p.ticker_count}종목`;
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

// 백그라운드 스캔 완료를 감지하는 폴링 주기. DB 한 행 + count 라 비용이 거의 없다.
const RUN_POLL_MS = 30_000;

export default function GlobalHeader() {
  const [remaining, setRemaining] = useState<number>(() =>
    msUntilClose(new Date()),
  );
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  // 오늘 런 기록(/run/today, DB 기반). 조회 실패면 null → 칩 숨김(가짜 정보 금지).
  const [scanStatus, setScanStatus] = useState<RunTodayResponse | null>(null);
  // 오늘 프리스캔 기록(/prefetch/today, DB 기반). 실패면 null → 칩 숨김(가짜 정보 금지).
  const [prefetchStatus, setPrefetchStatus] =
    useState<PrefetchTodayResponse | null>(null);
  // 직전 폴링의 finished_at — 값이 바뀌면 스캔이 새로 끝난 것.
  // undefined = 아직 첫 로드 전(기준점 미확보), null = 오늘 런 없음.
  const lastFinishedRef = useRef<string | null | undefined>(undefined);
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

  // 스캔 상태 칩 + 자동 갱신 폴링.
  // 스캔은 백그라운드 스케줄러(별도 실행 경로)가 돌리므로 UI 는 완료를 통보받을 방법이
  // 없다 — /run/today 를 주기 폴링해 finished_at 이 바뀌면 보드 재조회를 브로드캐스트한다.
  // (이게 없으면 15:20에 스캔이 끝나도 화면이 그대로라 수동 새로고침이 필요하다.)
  useEffect(() => {
    let alive = true;
    const load = () => {
      // 프리스캔 상태도 같은 주기로 갱신(프리페치 버튼 완료 시 emitRefetch 로도 즉시 갱신).
      fetchPrefetchToday()
        .then((p) => {
          if (alive) setPrefetchStatus(p);
        })
        .catch(() => {
          if (alive) setPrefetchStatus(null);
        });
      fetchRunToday()
        .then((s) => {
          if (!alive) return;
          setScanStatus(s);
          const previous = lastFinishedRef.current;
          lastFinishedRef.current = s.finished_at;
          // 첫 로드는 기준점만 잡는다(마운트마다 재조회가 터지지 않게).
          if (previous !== undefined && s.finished_at !== previous) {
            emitRefetch();
          }
        })
        .catch(() => {
          if (alive) setScanStatus(null);
        });
    };
    load();
    const id = window.setInterval(load, RUN_POLL_MS);
    window.addEventListener(REFETCH_EVENT, load);
    return () => {
      alive = false;
      window.clearInterval(id);
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
        {prefetchStatus && (
          <span
            className={`gh-prefetch-status ${
              prefetchStatus.ran ? 'is-done' : 'is-pending'
            }`}
            data-testid="prefetch-status"
            title={
              prefetchStatus.ran
                ? `오늘(${prefetchStatus.as_of}) 장전 프리스캔 완료 — ` +
                  `유니버스 ${prefetchStatus.universe_count}종목 / ` +
                  `FINAL 지표 ${prefetchStatus.ticker_count}종목`
                : '오늘 장전 프리스캔 기록이 없어요 — "종목 후보 가져오기"로 실행할 수 있어요'
            }
          >
            {prefetchChipLabel(prefetchStatus)}
          </span>
        )}
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
      </div>
    </div>
  );
}
