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
