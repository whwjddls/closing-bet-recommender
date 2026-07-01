import { useEffect, useState } from 'react';
import { fetchPerformance, type PerformanceResponse } from '../api/client';
import { formatPercent } from '../lib/format';
import PerfTable from '../components/PerfTable';
import MiniChart from '../components/MiniChart';

function pct(ratio: number): string {
  return `${Math.round(ratio * 100)}%`;
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

        <div data-testid="cum-curve">
          누적곡선{' '}
          <MiniChart data={a.cumulative_curve.map((c) => c.cum)} />
        </div>

        <div className="by-grade">
          {a.by_grade.map((g) => (
            <span key={g.grade} data-testid={`by-grade-${g.grade}`}>
              {g.grade} {pct(g.hit_rate)} (n={g.n})
            </span>
          ))}
        </div>

        <div className="by-regime">
          {a.by_regime.map((r) => (
            <span key={r.regime} data-testid={`by-regime-${r.regime}`}>
              레짐 {r.regime} {pct(r.hit_rate)} (n={r.n})
            </span>
          ))}
        </div>
      </section>

      <h2>어제 픽 (확정 채점)</h2>
      <PerfTable rows={data.picks} />
    </main>
  );
}
