import type { OvernightGap } from '../api/client';
import { formatPercent, directionClass } from '../lib/format';

// σ(변동성)는 부호 없는 크기라 formatPercent(+ 접두)를 쓰지 않고 절댓값 %로 표기.
function formatMagnitude(ratio: number, digits = 1): string {
  return `${(Math.abs(ratio) * 100).toFixed(digits)}%`;
}

// 종가→익일시가 오버나잇 갭 표본 통계.
// 정직성: 라벨에 표본 n·기간을 명시. 표본 부족(<20)이면 백엔드가 null → placeholder.
export default function OvernightGapStat({
  gap,
}: {
  gap: OvernightGap | null;
}) {
  if (!gap) {
    return (
      <section
        className="overnight-gap overnight-gap--empty"
        data-testid="overnight-gap"
        aria-label="오버나잇 갭 통계"
      >
        <h3 className="og-title">하룻밤 가격 변동(과거 통계)</h3>
        <p className="og-empty" data-testid="overnight-gap-empty">
          표본 부족(&lt;20일)
        </p>
      </section>
    );
  }

  const { mean, std, worst5pct, n } = gap;
  const meanDir = directionClass(mean);

  return (
    <section
      className="overnight-gap"
      data-testid="overnight-gap"
      aria-label="오버나잇 갭 통계"
    >
      <h3 className="og-title">
        하룻밤 가격 변동(과거 통계) ·{' '}
        <span className="og-scope">이 종목 과거 {n}일</span>
      </h3>

      <dl className="og-grid">
        <div className="og-cell">
          <dt>평균 변동</dt>
          <dd
            className={`og-val mono dir-${meanDir}`}
            data-testid="overnight-gap-mean"
          >
            {formatPercent(mean)}
          </dd>
        </div>
        <div className="og-cell">
          <dt>출렁임 σ</dt>
          <dd className="og-val mono og-neutral" data-testid="overnight-gap-std">
            {formatMagnitude(std)}
          </dd>
        </div>
        <div className="og-cell">
          <dt>최악 5%(하락)</dt>
          <dd
            className="og-val mono og-worst"
            data-testid="overnight-gap-worst"
            title="하위 5% 최악 오버나잇 갭(하방 꼬리)"
          >
            {formatPercent(worst5pct)}
          </dd>
        </div>
        <div className="og-cell">
          <dt>표본</dt>
          <dd className="og-val mono og-neutral" data-testid="overnight-gap-n">
            {n}
          </dd>
        </div>
      </dl>

      <p className="og-summary" data-testid="overnight-gap-summary">
        다음날 아침 평균{' '}
        <span className={`dir-${meanDir}`}>{formatPercent(mean)}</span> · 최악 5%{' '}
        <span className="og-worst">{formatPercent(worst5pct)}</span> · n={n}
      </p>
    </section>
  );
}
