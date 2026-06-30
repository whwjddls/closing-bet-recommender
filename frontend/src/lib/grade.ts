import type { Grade } from '../api/client';

// 백엔드와 동일 컷오프: S≥0.8 / A≥0.6 / B≥0.4 / C>0 (core 기준).
export function gradeFromCore(core: number): Grade {
  if (core >= 0.8) return 'S';
  if (core >= 0.6) return 'A';
  if (core >= 0.4) return 'B';
  return 'C';
}
