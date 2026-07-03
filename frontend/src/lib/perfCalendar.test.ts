import { describe, it, expect } from 'vitest';
import { deriveHeatmapCells } from './perfCalendar';

const curve = [
  { date: '2026-06-01', cum: 0.01 }, // 첫 점: cum 자체가 증분(스펙 규칙)
  { date: '2026-06-02', cum: 0.005 }, // 증분 -0.005 → loss
  { date: '2026-06-04', cum: 0.02 }, // 증분 +0.015 → win (6/3은 곡선에 없음 → skip)
];

describe('deriveHeatmapCells', () => {
  it('일별 증분 부호로 win/loss, 곡선에 없는 날은 skip', () => {
    const cells = deriveHeatmapCells(curve, [
      '2026-06-01',
      '2026-06-02',
      '2026-06-03',
      '2026-06-04',
    ]);
    expect(cells).toEqual([
      { date: '2026-06-01', kind: 'win', delta: 0.01 },
      { date: '2026-06-02', kind: 'loss', delta: -0.005 },
      { date: '2026-06-03', kind: 'skip', delta: null },
      { date: '2026-06-04', kind: 'win', delta: 0.015 },
    ]);
  });

  it('증분 0은 skip 취급(승도 패도 아님)', () => {
    const flat = [
      { date: '2026-06-01', cum: 0.01 },
      { date: '2026-06-02', cum: 0.01 },
    ];
    expect(deriveHeatmapCells(flat, ['2026-06-02'])[0].kind).toBe('skip');
  });

  it('빈 곡선 → 전부 skip', () => {
    expect(deriveHeatmapCells([], ['2026-06-01'])[0].kind).toBe('skip');
  });
});
