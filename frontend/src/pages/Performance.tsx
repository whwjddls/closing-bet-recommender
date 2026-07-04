import { useCallback, useEffect, useState } from 'react';
import { Calculator } from 'lucide-react';
import {
  fetchPerformance,
  fetchScoringStatus,
  triggerScoring,
  type PerformanceResponse,
  type RunStatusResponse,
} from '../api/client';
import { cachedFetch, invalidateCache } from '../lib/dataCache';
import { formatPercent } from '../lib/format';
import JobButton, { type JobToast } from '../components/JobButton';
import PerfTable from '../components/PerfTable';
import MonthlyPerfCalendar from '../components/MonthlyPerfCalendar';
import CumulativeCurve from '../components/CumulativeCurve';

// 채점 잡 완료 상태 → 초보자 친화 토스트. SCORED:n 은 채점 건수.
function scoringToast(status: RunStatusResponse): JobToast {
  if (status.last_error) return { tone: 'error', message: status.last_error };
  if (status.last_result === 'SKIPPED')
    return { tone: 'warn', message: '오늘은 휴장일이에요' };
  if (status.last_result?.startsWith('SCORED:')) {
    const n = Number(status.last_result.slice('SCORED:'.length));
    return n > 0
      ? { tone: 'ok', message: `${n}종목 채점 완료` }
      : {
          tone: 'warn',
          message: '채점할 픽이 없어요 — 어제 추천이 없었거나 이미 채점됐어요',
        };
  }
  return { tone: 'ok', message: status.last_result ?? '채점 완료' };
}

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
      title="성공률 신뢰구간(하한~상한). 넓을수록 표본이 얇아 신뢰도 낮음"
    >
      [{pct(low)}~{pct(high)}]
    </span>
  );
}

export default function Performance() {
  const [data, setData] = useState<PerformanceResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    cachedFetch('performance', fetchPerformance)
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 채점 완료 → 캐시 무효화 후 재조회(신선한 성공률 즉시 반영).
  const reloadAfterScoring = useCallback(() => {
    invalidateCache('performance');
    load();
  }, [load]);

  if (error)
    return <p data-testid="perf-error">성과를 불러오지 못했습니다: {error}</p>;
  if (!data) return <p>로딩 중…</p>;

  const a = data.aggregate;
  const hasBenchmark = a.benchmark_curve.length > 0;
  // 표본 0(콜드스타트 극단) → 리스크 지표는 아직 의미 없어 흐리게 처리.
  const noSample = a.sample_size === 0;

  return (
    <main>
      <div className="perf-head">
        <h1>성과 리포트{data.eval_date ? ` (${data.eval_date})` : ''}</h1>
        <JobButton
          idleLabel={
            <>
              <Calculator size={14} aria-hidden="true" /> 성과 채점하기
            </>
          }
          runningLabel="채점 중"
          hint="어제 픽의 아침(9~10시) 결과를 계산해요"
          trigger={triggerScoring}
          fetchStatus={fetchScoringStatus}
          describeResult={scoringToast}
          onDone={reloadAfterScoring}
          testId="job-scoring"
        />
      </div>

      <section
        data-testid="agg-panel"
        data-cold-start={a.cold_start}
        className={a.cold_start ? 'agg cold-start' : 'agg'}
      >
        {a.cold_start && (
          <p data-testid="cold-start-caption" className="cold-start-caption">
            아직 기록이 쌓이는 중 (표본 {a.sample_size} &lt; 30) — 성공률은
            참고용이에요.
          </p>
        )}
        <div className="agg-grid">
          <span data-testid="agg-hit-rate">
            성공률(다음날 아침 기준) <span className="mono">{pct(a.hit_rate)}</span>{' '}
            <span className="mono">(n={a.sample_size})</span>
          </span>
          <span>
            평균 아침 수익률{' '}
            <span className="mono">{formatPercent(a.avg_morning_return)}</span>
          </span>
        </div>

        {/* 리스크 지표 줄: 최대 하락폭(적색) · 손익비 · 최대연속손실 */}
        <div
          className={`agg-metrics${noSample ? ' agg-metrics--dim' : ''}`}
          data-testid="agg-metrics"
          data-no-sample={noSample}
        >
          <div className="metric metric--risk" data-testid="metric-mdd">
            <span className="metric-label">최대 하락폭</span>
            <span className="metric-val mono">{formatPercent(a.mdd)}</span>
          </div>
          <div className="metric" data-testid="metric-payoff">
            <span className="metric-label">손익비(이익÷손실)</span>
            <span className="metric-val mono">{a.payoff_ratio.toFixed(2)}</span>
          </div>
          <div className="metric" data-testid="metric-consec-losses">
            <span className="metric-label">최대 연속 실패</span>
            <span className="metric-val mono">{a.max_consec_losses}회</span>
          </div>
        </div>

        <div data-testid="cum-curve" className="cum-curve">
          <div className="cum-curve-head">
            <span>수익곡선 vs 코스피</span>
            {hasBenchmark && (
              <span className="cum-legend" data-testid="benchmark-legend">
                <span className="cum-legend-strategy">■</span> 이 전략{' '}
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
              {g.grade} <span className="mono">{pct(g.hit_rate)}</span>{' '}
              <span className="mono">(n={g.n})</span>{' '}
              <ConfidenceInterval low={g.ci_low} high={g.ci_high} />
            </span>
          ))}
        </div>

        <div className="by-regime">
          {a.by_regime.map((r) => (
            <span key={r.regime} data-testid={`by-regime-${r.regime}`}>
              장분위기 {r.regime} <span className="mono">{pct(r.hit_rate)}</span>{' '}
              <span className="mono">(n={r.n})</span>{' '}
              <ConfidenceInterval low={r.ci_low} high={r.ci_high} />
            </span>
          ))}
        </div>
      </section>

      <MonthlyPerfCalendar
        curve={a.cumulative_curve}
        sampleSize={a.sample_size}
      />

      <h2>어제 추천 성적표 (확정 채점)</h2>
      <PerfTable rows={data.picks} />
    </main>
  );
}
