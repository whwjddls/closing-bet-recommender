import type { Market, Recommendation } from '../api/client';

// 섹터 필드가 아직 없어 시장(KOSPI/KOSDAQ) 기준으로 분포·쏠림을 판정한다.
const CONCENTRATION_MIN_PICKS = 3; // 표본이 작을 때의 100% 오탐 방지
const CONCENTRATION_THRESHOLD = 0.8; // 한 시장 80%↑ 몰리면 경고

export interface MarketDistribution {
  KOSPI: number;
  KOSDAQ: number;
  total: number;
  dominant: Market | null;
  dominantShare: number;
  isConcentrated: boolean;
}

export function computeDistribution(
  recs: Recommendation[],
): MarketDistribution {
  const KOSPI = recs.filter((r) => r.market === 'KOSPI').length;
  const KOSDAQ = recs.filter((r) => r.market === 'KOSDAQ').length;
  const total = recs.length;
  let dominant: Market | null = null;
  let dominantShare = 0;
  if (total > 0) {
    dominant = KOSPI >= KOSDAQ ? 'KOSPI' : 'KOSDAQ';
    dominantShare = Math.max(KOSPI, KOSDAQ) / total;
  }
  const isConcentrated =
    total >= CONCENTRATION_MIN_PICKS &&
    dominantShare >= CONCENTRATION_THRESHOLD;
  return { KOSPI, KOSDAQ, total, dominant, dominantShare, isConcentrated };
}

function csvCell(value: string): string {
  return /[",\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

// 담은 픽을 종목/코드/등급/매수가/청산 CSV 텍스트로 직렬화(순수 함수).
export function buildPicksCsv(recs: Recommendation[]): string {
  const header = ['종목', '코드', '등급', '매수가', '청산'];
  const lines = [header.join(',')];
  for (const r of recs) {
    const buy = r.buy_price_final ?? r.buy_price_provisional;
    lines.push(
      [
        csvCell(r.name),
        csvCell(r.ticker),
        csvCell(r.grade),
        csvCell(String(buy)),
        csvCell(r.exit_label),
      ].join(','),
    );
  }
  return lines.join('\n');
}

function downloadCsv(recs: Recommendation[]): void {
  const csv = buildPicksCsv(recs);
  // jsdom 등 Blob URL 미지원 환경에서는 조용히 no-op(테스트 안전).
  if (
    typeof URL === 'undefined' ||
    typeof URL.createObjectURL !== 'function'
  ) {
    return;
  }
  // Excel 한글 인식용 BOM 선행.
  const blob = new Blob(['﻿' + csv], {
    type: 'text/csv;charset=utf-8;',
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `picks-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// Board 하단 고정 트레이. 클라이언트 상태만 사용(신규 API 없음).
export default function PicksTray({
  picks,
  onRemove,
  onClear,
}: {
  picks: Recommendation[];
  onRemove: (ticker: string) => void;
  onClear?: () => void;
}) {
  // 빈 상태에선 하단 부유 밴드를 아예 렌더하지 않는다(픽을 담으면 등장).
  if (picks.length === 0) return null;

  const dist = computeDistribution(picks);

  return (
    <div
      className="picks-tray"
      data-testid="picks-tray"
      role="region"
      aria-label="담기 트레이"
    >
      <div className="picks-chips" data-testid="picks-chips">
            {picks.map((r) => (
              <span
                key={r.ticker}
                data-testid="pick-chip"
                className={`pick-chip grade-${r.grade}`}
              >
                <span className={`grade-badge grade-${r.grade}`}>
                  {r.grade}
                </span>
                <span className="pick-chip-name">{r.name}</span>
                <button
                  type="button"
                  className="pick-chip-x"
                  aria-label={`${r.name} 빼기`}
                  onClick={() => onRemove(r.ticker)}
                >
                  ×
                </button>
              </span>
            ))}
          </div>

          <div className="picks-meta">
            <span className="picks-count" data-testid="picks-count">
              {dist.total}종목
            </span>
            <span className="picks-dist" data-testid="picks-dist">
              KOSPI {dist.KOSPI} · KOSDAQ {dist.KOSDAQ}
            </span>
            {dist.isConcentrated && (
              <span
                className="picks-warn"
                data-testid="picks-concentration-warning"
                role="alert"
              >
                ⚠ {dist.dominant} {Math.round(dist.dominantShare * 100)}% 쏠림
              </span>
            )}
            {onClear && (
              <button
                type="button"
                className="picks-clear"
                onClick={onClear}
              >
                비우기
              </button>
            )}
            <button
              type="button"
              className="picks-csv"
              data-testid="picks-csv-export"
              onClick={() => downloadCsv(picks)}
            >
              CSV 내보내기
            </button>
          </div>
    </div>
  );
}

// 트레이가 하단 고정으로 마지막 콘텐츠를 가리지 않도록 하는 스페이서.
export function PicksTraySpacer() {
  return <div className="picks-tray-spacer" aria-hidden="true" />;
}
