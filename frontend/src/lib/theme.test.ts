import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getStoredTheme,
  applyTheme,
  persistTheme,
  initTheme,
  toggleTheme,
  THEME_EVENT,
} from './theme';

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe('theme lib', () => {
  it('저장값이 없으면 기본은 다크다', () => {
    expect(getStoredTheme()).toBe('dark');
  });

  it('applyTheme는 문서 루트에 data-theme를 세팅한다', () => {
    applyTheme('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    applyTheme('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('persist → getStored 왕복이 유지된다', () => {
    persistTheme('light');
    expect(getStoredTheme()).toBe('light');
  });

  it('initTheme는 저장된 테마를 적용하고 반환한다', () => {
    persistTheme('light');
    expect(initTheme()).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('toggleTheme는 반대로 전환+적용+저장한다', () => {
    const next = toggleTheme('dark');
    expect(next).toBe('light');
    expect(document.documentElement.dataset.theme).toBe('light');
    expect(getStoredTheme()).toBe('light');

    const back = toggleTheme('light');
    expect(back).toBe('dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(getStoredTheme()).toBe('dark');
  });

  it('applyTheme는 THEME_EVENT를 발행한다(canvas 차트 재도색용)', () => {
    const seen = vi.fn();
    window.addEventListener(THEME_EVENT, seen);
    applyTheme('light');
    expect(seen).toHaveBeenCalledTimes(1);
    window.removeEventListener(THEME_EVENT, seen);
  });
});
