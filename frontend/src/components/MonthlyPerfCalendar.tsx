import type { CurvePoint } from '../api/client';
import { kstToday } from '../lib/date';
import { deriveHeatmapCells, weekAlignedDates } from '../lib/perfCalendar';
import { formatPercent } from '../lib/format';

// 성과 페이지 월 잔디 — 최근 weeks주(기본 13≈3개월) 요일정렬 격자. 스펙 §2.3.
// props 주도(성과 페이지 aggregate 재사용 — 이중 fetch 없음).
const DEFAULT_WEEKS = 13;
const WD_LABELS = ['', '월', '', '수', '', '금', '']; // sparse 요일 라벨

export default function MonthlyPerfCalendar({
  curve,
  sampleSize,
  weeks = DEFAULT_WEEKS,
}: {
  curve: CurvePoint[];
  sampleSize: number;
  weeks?: number;
}) {
  const empty = sampleSize === 0;

  return (
    <section
      className="monthly-perf-calendar"
      data-testid="monthly-perf-calendar"
      aria-label="성과 달력(최근 3개월)"
    >
      <div className="mcal-head">
        <span className="mcal-title">성과 달력 · 최근 3개월</span>
        <span className="mcal-legend" data-testid="mcal-legend">
          <span className="mcal-dot mcal-dot--win" /> 성공
          <span className="mcal-dot mcal-dot--loss" /> 실패
          <span className="mcal-dot mcal-dot--skip" /> 관망
        </span>
      </div>

      {empty ? (
        <p className="mcal-empty" data-testid="mcal-empty">
          아직 기록이 없어요 — 첫 채점부터 채워져요
        </p>
      ) : (
        <MonthlyGrid curve={curve} weeks={weeks} />
      )}
    </section>
  );
}

function MonthlyGrid({
  curve,
  weeks,
}: {
  curve: CurvePoint[];
  weeks: number;
}) {
  const dates = weekAlignedDates(kstToday(), weeks);
  const cells = deriveHeatmapCells(curve, dates);
  const wins = cells.filter((c) => c.kind === 'win').length;
  const losses = cells.filter((c) => c.kind === 'loss').length;

  // 월 라벨: 각 주(열)의 첫 날(일요일) 기준 달이 바뀌면 표기.
  const monthLabels = Array.from({ length: weeks }, (_, w) => {
    const first = dates[w * 7];
    const prev = w > 0 ? dates[(w - 1) * 7] : null;
    const m = first.slice(5, 7);
    if (prev && prev.slice(5, 7) === m) return '';
    return `${Number(m)}월`;
  });

  return (
    <>
      <div className="mcal-body">
        <div className="mcal-weekdays" aria-hidden="true">
          {WD_LABELS.map((w, i) => (
            <span key={i} className="mcal-wd">
              {w}
            </span>
          ))}
        </div>
        <div className="mcal-cols">
          <div className="mcal-months" aria-hidden="true">
            {monthLabels.map((m, i) => (
              <span key={i} className="mcal-month">
                {m}
              </span>
            ))}
          </div>
          <div
            className="mcal-grid"
            style={{ gridTemplateColumns: `repeat(${weeks}, 1fr)` }}
          >
            {cells.map((c) => (
              <span
                key={c.date}
                className="mcal-cell"
                data-testid="mcal-cell"
                data-kind={c.kind}
                title={
                  c.delta === null
                    ? `${c.date} · 관망`
                    : `${c.date} · ${formatPercent(c.delta)}`
                }
              />
            ))}
          </div>
        </div>
      </div>
      <p className="mcal-count mono">
        성공 {wins} · 실패 {losses}
      </p>
    </>
  );
}
