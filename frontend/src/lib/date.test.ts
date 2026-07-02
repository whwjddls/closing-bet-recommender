import { describe, it, expect } from 'vitest';
import { kstToday } from './date';

describe('kstToday', () => {
  it('UTC 자정 직후(00:30 UTC)라도 KST 기준 당일 날짜를 준다', () => {
    // 2026-07-03 00:30:00 UTC == 2026-07-03 09:30 KST → 07-03
    const t = Date.UTC(2026, 6, 3, 0, 30, 0);
    expect(kstToday(t)).toBe('2026-07-03');
  });

  it('UTC 기준 어제/오늘이 갈리는 시각(15:20 UTC = 익일 00:20 KST)에 KST 익일을 준다', () => {
    // 2026-07-02 15:20:00 UTC == 2026-07-03 00:20 KST → 07-03 (UTC라면 07-02)
    const t = Date.UTC(2026, 6, 2, 15, 20, 0);
    expect(kstToday(t)).toBe('2026-07-03');
    // 같은 순간을 UTC로 자르면 하루 밀린다(회귀 방지의 근거).
    expect(new Date(t).toISOString().slice(0, 10)).toBe('2026-07-02');
  });

  it('KST 자정 직전(14:59 UTC = 23:59 KST)은 아직 당일', () => {
    const t = Date.UTC(2026, 6, 2, 14, 59, 0);
    expect(kstToday(t)).toBe('2026-07-02');
  });
});
