import { describe, it, expect } from 'vitest';
import { deriveHeatmapCells, weekAlignedDates } from './perfCalendar';

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

describe('weekAlignedDates', () => {
  it('anchor가 속한 주의 토요일에서 끝나고 일요일에서 시작한다', () => {
    // 2026-07-01은 수요일. 2주(14일) 격자.
    const dates = weekAlignedDates('2026-07-01', 2);
    expect(dates).toHaveLength(14);
    // 첫 날은 일요일(2026-06-21), 마지막 날은 토요일(2026-07-04)
    expect(dates[0]).toBe('2026-06-21');
    expect(dates[13]).toBe('2026-07-04');
    // 요일 정렬 검증: 인덱스 0,7 은 일요일
    const dow = (d: string) => new Date(d + 'T00:00:00Z').getUTCDay();
    expect(dow(dates[0])).toBe(0);
    expect(dow(dates[7])).toBe(0);
    expect(dow(dates[6])).toBe(6);
  });

  it('anchor가 토요일이면 그 주가 마지막 열이다', () => {
    const dates = weekAlignedDates('2026-07-04', 1); // 토요일
    expect(dates).toHaveLength(7);
    expect(dates[0]).toBe('2026-06-28'); // 일
    expect(dates[6]).toBe('2026-07-04'); // 토(=anchor)
  });
});
