import { describe, it, expect } from 'vitest';
import { formatPrice, formatPercent } from './format';

describe('format', () => {
  it('가격은 천단위 콤마', () => {
    expect(formatPrice(24500)).toBe('24,500');
  });
  it('퍼센트는 소수2 + %', () => {
    expect(formatPercent(0.0053)).toBe('+0.53%');
    expect(formatPercent(-0.0037)).toBe('-0.37%');
  });
  it('null/undefined 퍼센트는 N/A (0점 처리 금지 신호)', () => {
    expect(formatPercent(null)).toBe('N/A');
  });
});
