// 성과 잔디(내 전략의 달력) 셀 파생 — /performance aggregate.cumulative_curve 기반.
// 스펙 §2.1: 증분>0 win(빨강)·<0 loss(파랑)·곡선에 없는 날/증분0 skip(회색).
// 첫 점 규칙: cum[0] 자체를 그날의 증분으로 취급.
import type { CurvePoint } from '../api/client'; // client.ts 기존 타입 재사용(드리프트 방지)

export type HeatCellKind = 'win' | 'loss' | 'skip';

export interface HeatCell {
  date: string;
  kind: HeatCellKind;
  delta: number | null;
}

export function deriveHeatmapCells(
  curve: CurvePoint[],
  dates: string[],
): HeatCell[] {
  const deltaByDate = new Map<string, number>();
  curve.forEach((p, i) => {
    deltaByDate.set(p.date, i === 0 ? p.cum : p.cum - curve[i - 1].cum);
  });
  return dates.map((date) => {
    const delta = deltaByDate.get(date);
    if (delta === undefined || delta === 0) {
      return { date, kind: 'skip' as const, delta: delta ?? null };
    }
    return { date, kind: delta > 0 ? ('win' as const) : ('loss' as const), delta };
  });
}

const WEEK_DAY_MS = 86_400_000;

// GitHub식 잔디용 날짜열: anchorToday가 속한 주의 토요일에서 끝나고
// weeks주 거슬러 올라간 일요일에서 시작(길이 weeks×7, 일→토 순).
// 요일은 UTC 자정 기준으로 TZ 불변 계산.
export function weekAlignedDates(anchorToday: string, weeks: number): string[] {
  const anchorMs = Date.parse(anchorToday + 'T00:00:00Z');
  const dow = new Date(anchorMs).getUTCDay(); // 0=일
  const endMs = anchorMs + (6 - dow) * WEEK_DAY_MS; // 이번 주 토요일
  const total = weeks * 7;
  const startMs = endMs - (total - 1) * WEEK_DAY_MS;
  return Array.from({ length: total }, (_, i) =>
    new Date(startMs + i * WEEK_DAY_MS).toISOString().slice(0, 10),
  );
}
