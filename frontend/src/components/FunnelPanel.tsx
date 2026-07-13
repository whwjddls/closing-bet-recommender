import type { RecommendationsResponse } from '../api/client';
import { useFlashOnChange } from '../lib/useFlashOnChange';
import Skeleton from './Skeleton';

// 오늘의 걸러내기 — 후보 풀에서 최종 추천까지. 추천 0건인 날 "왜"를 숫자로 설명한다.
// 백엔드 퍼널(/run/today.funnel)이 있으면 단계별 탈락 수를 그대로 노출한다 — "신호 통과 0"
// 만 보면 전략이 보수적이라 그런 건지 특정 게이트가 버그로 전멸시킨 건지 구분할 수 없다.
// 퍼널이 없는 날(구 런 기록)은 기존 파생 사유로 폴백한다.
interface FunnelPanelProps {
  universeCount: number | null; // /universe rows 수 — 프리페치 전이면 null/0
  board: RecommendationsResponse | null; // 보드 응답 — 로딩 전 null
  funnel?: Record<string, number> | null; // 단계별 생존 수 — 없으면 폴백
}

// 탈락 사유 라벨 — 0인 항목은 노이즈라 감춘다.
const DROP_LABELS: ReadonlyArray<[string, string]> = [
  ['shin_zero', '돌파 미달'],
  ['veto_blocked', '공시 veto'],
  ['regime_zero', '리스크오프'],
  ['final_hygiene_dropped', '최종 위생'],
];

export default function FunnelPanel({
  universeCount,
  board,
  funnel,
}: FunnelPanelProps) {
  const candidates =
    funnel?.candidates ||
    (universeCount && universeCount > 0 ? universeCount : null);

  let picks = '—';
  let reason: string | null = null;
  let coverage: string | null = null;
  if (board) {
    if (!board.data_available) {
      reason = '데이터 없음 — 발행 보류';
    } else {
      picks = String(board.recommendations.length);
      coverage = `커버리지 ${board.kis_coverage_pct.toFixed(1)}%`;
      if (board.recommendations.length === 0) {
        reason = '신호 통과 0 — 오늘은 관망';
      }
    }
  }

  const drops = funnel
    ? DROP_LABELS.filter(([key]) => (funnel[key] ?? 0) > 0).map(
        ([key, label]) => `${label} ${funnel[key]}`,
      )
    : [];

  // 스캔 완료로 추천 수가 바뀔 때만 짧게 강조(모션② — 매초 시계엔 미적용).
  const flash = useFlashOnChange(picks);

  return (
    <section
      className="funnel-panel"
      data-testid="funnel-panel"
      aria-label="오늘의 걸러내기"
    >
      <div className="fp-head">
        <span className="fp-title">오늘의 걸러내기</span>
        {coverage && <span className="fp-cov mono">{coverage}</span>}
      </div>

      {board === null ? (
        <Skeleton lines={2} />
      ) : (
        <>
          <p
            className={`fp-flow${flash ? ' tick-flash' : ''}`}
            data-testid="funnel-flow"
          >
            <span className="fp-num mono">{candidates ?? '—'}</span>
            <span className="fp-arrow" aria-hidden="true">
              →
            </span>
            <span className="fp-num fp-final mono">{picks}</span>
          </p>
          <p className="fp-legend">종목 후보 → 오늘의 추천</p>
          {drops.length > 0 && (
            <p className="fp-drops mono" data-testid="funnel-drops">
              탈락: {drops.join(' · ')}
            </p>
          )}
          {reason && (
            <p className="fp-reason" data-testid="funnel-reason">
              {reason}
            </p>
          )}
        </>
      )}
    </section>
  );
}
