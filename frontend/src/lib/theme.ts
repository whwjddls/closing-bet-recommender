// 라이트/다크 테마 토글 (§1-4). 기본은 다크(:root 토큰).
// data-theme='light' 를 문서 루트에 붙이면 theme.css의 라이트 오버라이드가 적용된다.
// 선택은 localStorage에 저장해 재방문/새로고침에도 유지한다.

export type Theme = 'dark' | 'light';

const STORAGE_KEY = 'closingbet:theme';

// 저장된 테마(없거나 오류면 기본 다크).
export function getStoredTheme(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'light' ? 'light' : 'dark';
  } catch {
    return 'dark';
  }
}

// 테마 변경 브로드캐스트 — canvas 차트(lightweight-charts)는 CSS 변수가
// 자동 적용되지 않아, 구독 컴포넌트가 현재 토큰으로 다시 그린다.
export const THEME_EVENT = 'closingbet:theme';

// 문서 루트에 테마를 반영. dark/light 모두 명시적으로 표기한다.
export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme;
  window.dispatchEvent(new CustomEvent(THEME_EVENT, { detail: theme }));
}

export function persistTheme(theme: Theme): void {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* 프라이빗 모드 등 저장 불가 — 조용히 무시 */
  }
}

// 앱 시작 시 1회 — 저장된 테마를 문서에 적용(플래시 방지). 적용된 테마 반환.
export function initTheme(): Theme {
  const theme = getStoredTheme();
  applyTheme(theme);
  return theme;
}

// 현재 테마 반대로 전환 + 적용 + 저장. 새 테마 반환.
export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === 'dark' ? 'light' : 'dark';
  applyTheme(next);
  persistTheme(next);
  return next;
}
