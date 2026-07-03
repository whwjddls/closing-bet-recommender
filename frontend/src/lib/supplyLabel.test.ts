import { describe, it, expect } from 'vitest';
import { formatSupplyToday } from './supplyLabel';

describe('formatSupplyToday', () => {
  it('백엔드 잠정 라벨을 풀네임으로 변환한다(축약 금지 — 사용자 요구)', () => {
    expect(formatSupplyToday('외인▲기관▲')).toBe('외국인+ 기관+');
    expect(formatSupplyToday('외인▲')).toBe('외국인+');
    expect(formatSupplyToday('기관▲')).toBe('기관+');
  });

  it('라벨 없음(null/undefined)은 —', () => {
    expect(formatSupplyToday(null)).toBe('—');
    expect(formatSupplyToday(undefined)).toBe('—');
  });

  it('미지의 포맷은 가공하지 않고 원문 그대로(정직성)', () => {
    expect(formatSupplyToday('연기금▲')).toBe('연기금▲');
  });
});
