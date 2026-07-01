import { useEffect, useState } from 'react';
import { fetchRecommendations, type RegimeInfo } from '../api/client';

type Verdict = 'GO' | 'CAUTION' | 'RISK_OFF';

const VERDICT_LABEL: Record<Verdict, string> = {
  GO: 'GO (공격 1.0x)',
  CAUTION: '보수 (사이즈 절반)',
  RISK_OFF: 'RISK-OFF (스킵)',
};

function todayKst(): string {
  const kst = new Date(Date.now() + 9 * 3600 * 1000);
  return kst.toISOString().slice(0, 10);
}

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

function formatCountdown(ms: number): string {
  if (ms <= 0) return '마감';
  const total = Math.floor(ms / 1000);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

// 데이터 기준 시각(HH:MM:SS, KST).
function formatKstClock(d: Date): string {
  const kst = new Date(d.getTime() + 9 * 3600 * 1000);
  return kst.toISOString().slice(11, 19);
}

// 데이터 나이(초). 미래 시각/시계 오차는 0으로 클램프.
function ageSeconds(nowMs: number, at: Date): number {
  return Math.max(0, Math.floor((nowMs - at.getTime()) / 1000));
}

function urgencyClass(ms: number): string {
  if (ms <= 0) return 'gh-closed';
  if (ms < 60 * 1000) return 'gh-danger'; // 1분 미만 적색 점멸
  if (ms < 5 * 60 * 1000) return 'gh-warn'; // 5분 미만 앰버
  return '';
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
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  // 보드 데이터를 받은 클라이언트 기준 시각(run_date는 날짜뿐이라 신선도 계산 불가).
  const [dataAt, setDataAt] = useState<Date | null>(null);

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setRemaining(msUntilClose(now));
      setNowMs(now.getTime());
    };
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    let alive = true;
    fetchRecommendations(todayKst())
      .then((board) => {
        if (!alive) return;
        setVerdict(deriveVerdict(Object.values(board.regimes)));
        setDataAt(new Date());
      })
      .catch(() => {
        /* 정직성 배너·카운트다운은 데이터 없이도 상시 노출 */
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="global-header" data-testid="global-header" role="banner">
      <div className="gh-left">
        <span className="gh-logo">종가베팅</span>
        <span
          className={`gh-countdown ${urgencyClass(remaining)}`}
          data-testid="close-countdown"
          title="15:30 KST 마감까지"
        >
          ⏱ 마감까지 {formatCountdown(remaining)}
        </span>
        {dataAt && (
          <span
            className="gh-timestamp"
            data-testid="data-timestamp"
            title="데이터 기준 시각 · 경과 시간"
          >
            기준 {formatKstClock(dataAt)} · {ageSeconds(nowMs, dataAt)}초 전
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

      <div className="gh-right" data-testid="honesty-banner">
        ⚠ 15:20 잠정 · 수급 D-1 · 체결 미연동
      </div>
    </div>
  );
}
