import { useEffect, useState } from 'react';
import Skeleton from './Skeleton';
import { Link } from 'react-router-dom';
import { CircleCheck, CircleX } from 'lucide-react';
import {
  fetchPerformance,
  type PerformanceResponse,
  type PickResult,
} from '../api/client';
import { cachedFetch } from '../lib/dataCache';
import { formatPercent, directionClass } from '../lib/format';

// 보드 우측 위젯 스택 최상단의 컴팩트 "어제 성과" 카드.
// 전략의 나머지 절반(청산 결과)을 한 화면에서 바로 확인시켜 준다.
// 클릭하면 /performance 상세로 이동. 표본이 없으면 정직하게 "기록 없음".

// 성공률은 다음날 아침(09~10시 VWAP) 기준. 비율 → 정수 %.
function pct(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

function OutcomeIcon({ outcome }: { outcome: PickResult['outcome'] }) {
  if (outcome === 'SUCCESS')
    return <CircleCheck size={12} className="dir-up" aria-hidden="true" />;
  if (outcome === 'FAIL')
    return <CircleX size={12} className="dir-down" aria-hidden="true" />;
  return <span aria-hidden="true">·</span>;
}

export default function PerfSummaryCard() {
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch('performance', fetchPerformance)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  // 로딩(캐시/네트워크 대기)
  if (!data && !failed) {
    return (
      <aside
        className="perf-summary-card"
        data-testid="perf-summary-card"
        aria-label="어제 성과 요약"
        aria-busy="true"
      >
        <h3 className="psc-title">어제 성과</h3>
        <Skeleton lines={2} />
      </aside>
    );
  }

  const agg = data?.aggregate;
  const picks = data?.picks ?? [];

  // 실패했거나 표본이 없으면 정직하게 "기록 없음"(그래도 상세로는 이동 가능).
  if (failed || !agg || agg.sample_size === 0) {
    return (
      <Link
        to="/performance"
        className="perf-summary-card perf-summary-card--empty"
        data-testid="perf-summary-card"
        aria-label="어제 성과 — 아직 기록 없음"
      >
        <h3 className="psc-title">어제 성과</h3>
        <p className="psc-empty" data-testid="perf-summary-empty">
          아직 기록이 없어요
        </p>
      </Link>
    );
  }

  const recentPicks = picks.slice(0, 2);

  return (
    <Link
      to="/performance"
      className="perf-summary-card"
      data-testid="perf-summary-card"
      aria-label="어제 성과 요약 — 성과 리포트로 이동"
    >
      <div className="psc-head">
        <h3 className="psc-title">어제 성과</h3>
        <span className="psc-more" aria-hidden="true">
          자세히 →
        </span>
      </div>

      <div className="psc-stats">
        <span
          className="psc-stat"
          data-testid="perf-summary-hitrate"
          title="다음날 아침(09~10시 VWAP) 기준 성공률"
        >
          <span className="psc-stat-val mono">{pct(agg.hit_rate)}</span>
          <span className="psc-stat-label">성공률 (n={agg.sample_size})</span>
        </span>
        <span className="psc-stat">
          <span className="psc-stat-val mono">
            {formatPercent(agg.avg_morning_return)}
          </span>
          <span className="psc-stat-label">평균 아침 수익률</span>
        </span>
      </div>

      {recentPicks.length > 0 && (
        <ul className="psc-picks" data-testid="perf-summary-picks">
          {recentPicks.map((p, i) => (
            <li
              key={`${p.ticker}-${i}`}
              className="psc-pick"
              data-testid="perf-summary-pick"
              data-outcome={p.outcome}
            >
              <span className="psc-pick-icon">
                <OutcomeIcon outcome={p.outcome} />
              </span>
              <span className="psc-pick-name">{p.name}</span>
              {p.morning_return != null && (
                <span
                  className={`psc-pick-ret mono dir-${directionClass(
                    p.morning_return,
                  )}`}
                >
                  {formatPercent(p.morning_return)}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </Link>
  );
}
