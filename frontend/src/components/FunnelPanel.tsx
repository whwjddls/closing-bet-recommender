import type { RecommendationsResponse } from '../api/client';

// 오늘의 걸러내기 — 후보 풀에서 최종 추천까지. 추천 0건인 날 "왜"를 숫자로 설명한다.
// v1은 가용 데이터만(후보 수·추천 수·커버리지) 사용, 사유는 프론트 파생(스펙 §2.1):
//   data_available=false → 데이터 없음 / 발행+추천0 → 신호 통과 0(관망).
// 단계별 상세 카운트(위생·레짐·veto 탈락 수)는 백엔드 확장 후(백로그 P2).
interface FunnelPanelProps {
  universeCount: number | null; // /universe rows 수 — 프리페치 전이면 null/0
  board: RecommendationsResponse | null; // 보드 응답 — 로딩 전 null
}

export default function FunnelPanel({ universeCount, board }: FunnelPanelProps) {
  const candidates =
    universeCount && universeCount > 0 ? String(universeCount) : '—';

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
        <p className="fp-skeleton" aria-busy="true">
          집계 중…
        </p>
      ) : (
        <>
          <p className="fp-flow" data-testid="funnel-flow">
            <span className="fp-num mono">{candidates}</span>
            <span className="fp-arrow" aria-hidden="true">
              →
            </span>
            <span className="fp-num fp-final mono">{picks}</span>
          </p>
          <p className="fp-legend">종목 후보 → 오늘의 추천</p>
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
