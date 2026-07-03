import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchPerformance, type PerformanceResponse } from '../api/client';
import { cachedFetch } from '../lib/dataCache';
import { kstToday } from '../lib/date';
import { deriveHeatmapCells, type HeatCell } from '../lib/perfCalendar';
import { formatPercent } from '../lib/format';

// 내 전략의 달력(성과 잔디) — 보드 레일 패널. 스펙 2026-07-04 §2.1.
// 최근 42일(달력일, KST)의 일별 성과를 셀로: 성공 빨강·실패 파랑·관망 회색.
// 표본 0/조회 실패는 컨테이너 안에서 정직한 빈 상태(추측 표시 금지).
const DAYS = 42;
const DAY_MS = 86_400_000;

function recentDates(): string[] {
  const now = Date.now();
  return Array.from({ length: DAYS }, (_, i) =>
    kstToday(now - (DAYS - 1 - i) * DAY_MS),
  );
}

export default function PerfHeatmap() {
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

  const empty = failed || (data !== null && data.aggregate.sample_size === 0);
  const cells: HeatCell[] =
    !data || empty
      ? []
      : deriveHeatmapCells(data.aggregate.cumulative_curve, recentDates());
  const wins = cells.filter((c) => c.kind === 'win').length;
  const losses = cells.filter((c) => c.kind === 'loss').length;

  return (
    <Link
      to="/performance"
      className="perf-heatmap"
      data-testid="perf-heatmap"
      aria-label="내 전략의 달력 — 성과 리포트로 이동"
    >
      <div className="ph-head">
        <span className="ph-title">내 전략의 달력</span>
        {!empty && data !== null && (
          <span className="ph-count mono">
            성공 {wins} · 실패 {losses}
          </span>
        )}
      </div>

      {empty ? (
        <p className="ph-empty" data-testid="perf-heatmap-empty">
          아직 기록이 없어요 — 첫 채점부터 채워져요
        </p>
      ) : data === null ? (
        <p className="ph-empty">로딩 중…</p>
      ) : (
        <div className="ph-grid" aria-hidden="true">
          {cells.map((c) => (
            <span
              key={c.date}
              className="ph-cell"
              data-testid="heat-cell"
              data-kind={c.kind}
              title={
                c.delta === null
                  ? `${c.date} · 관망`
                  : `${c.date} · ${formatPercent(c.delta)}`
              }
            />
          ))}
        </div>
      )}
    </Link>
  );
}
