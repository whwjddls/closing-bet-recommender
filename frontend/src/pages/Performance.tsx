import { useEffect, useState } from 'react';
import { fetchPerformance, type PerformanceResponse } from '../api/client';
import { formatPercent } from '../lib/format';
import PerfTable from '../components/PerfTable';
import CumulativeCurve from '../components/CumulativeCurve';

function pct(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
}

// 신뢰구간이 넓으면(하한~상한 30%p 초과) 흐리게 — 표본이 얇아 신뢰도 낮음.
const CI_WIDE_THRESHOLD = 0.3;

function ConfidenceInterval({
  low,
  high,
}: {
  low: number;
  high: number;
}) {
  const wide = high - low > CI_WIDE_THRESHOLD;
  return (
    <span
      className={`ci${wide ? ' ci-wide' : ''}`}
      data-testid="ci"
      data-wide={wide}
      title="적중률 신뢰구간(하한~상한)"
    >
      [{pct(low)}~{pct(high)}]
    </span>
  );
}

export default function Performance() {
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchPerformance()
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error)
    return <p data-testid="perf-error">성과를 불러오지 못했습니다: {error}</p>;
  if (!data) return <p>로딩 중…</p>;

  const a = data.aggregate;
  const hasBenchmark = a.benchmark_curve.length > 0;

  return (
    <main>
      <h1>성과 추적 ({data.eval_date})</h1>

      <section
        data-testid="agg-panel"
        data-cold-start={a.cold_start}
        className={a.cold_start ? 'agg cold-start' : 'agg'}
      >
        {a.cold_start && (
          <p data-testid="cold-start-caption" className="cold-start-caption">
            데이터 누적 중 (표본 {a.sample_size} &lt; 30) — 적중률은 참고용입니다.
          </p>
        )}
        <div className="agg-grid">
          <span data-testid="agg-hit-rate">
            적중률 {pct(a.hit_rate)} (n={a.sample_size})
          </span>
          <span>평균 오전수익률 {formatPercent(a.avg_morning_return)}</span>
        </div>

        {/* 리스크 지표 줄: MDD(적색) · 손익비 · 최대연속손실 */}
        <div className="agg-metrics" data-testid="agg-metrics">
          <div className="metric metric--risk" data-testid="metric-mdd">
            <span className="metric-label">MDD</span>
            <span className="metric-val mono">{formatPercent(a.mdd)}</span>
          </div>
          <div className="metric" data-testid="metric-payoff">
            <span className="metric-label">손익비</span>
            <span className="metric-val mono">{a.payoff_ratio.toFixed(2)}</span>
          </div>
          <div className="metric" data-testid="metric-consec-losses">
            <span className="metric-label">최대 연속손실</span>
            <span className="metric-val mono">{a.max_consec_losses}회</span>
          </div>
        </div>

        <div data-testid="cum-curve" className="cum-curve">
          <div className="cum-curve-head">
            <span>누적곡선</span>
            {hasBenchmark && (
              <span className="cum-legend" data-testid="benchmark-legend">
                <span className="cum-legend-strategy">■</span> 전략{' '}
                <span className="cum-legend-bench">■</span> 코스피
              </span>
            )}
          </div>
          <CumulativeCurve
            strategy={a.cumulative_curve.map((c) => c.cum)}
            benchmark={
              hasBenchmark ? a.benchmark_curve.map((c) => c.cum) : undefined
            }
          />
        </div>

        <div className="by-grade">
          {a.by_grade.map((g) => (
            <span key={g.grade} data-testid={`by-grade-${g.grade}`}>
              {g.grade} {pct(g.hit_rate)} (n={g.n}){' '}
              <ConfidenceInterval low={g.ci_low} high={g.ci_high} />
            </span>
          ))}
        </div>

        <div className="by-regime">
          {a.by_regime.map((r) => (
            <span key={r.regime} data-testid={`by-regime-${r.regime}`}>
              레짐 {r.regime} {pct(r.hit_rate)} (n={r.n}){' '}
              <ConfidenceInterval low={r.ci_low} high={r.ci_high} />
            </span>
          ))}
        </div>
      </section>

      <h2>어제 픽 (확정 채점)</h2>
      <PerfTable rows={data.picks} />
    </main>
  );
}
