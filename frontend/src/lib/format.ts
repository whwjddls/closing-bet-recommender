export function formatPrice(n: number | null | undefined): string {
  if (n === null || n === undefined) return 'N/A';
  return n.toLocaleString('ko-KR');
}

export function formatPercent(
  ratio: number | null | undefined,
  digits = 2,
): string {
  if (ratio === null || ratio === undefined) return 'N/A';
  const pct = ratio * 100;
  const sign = pct > 0 ? '+' : '';
  return `${sign}${pct.toFixed(digits)}%`;
}

// 한국 관례 방향색: 양(+)=상승(up/빨강), 음(−)=하락(down/파랑), 0/미확정=flat.
export type Direction = 'up' | 'down' | 'flat';

export function directionClass(
  value: number | null | undefined,
): Direction {
  if (value === null || value === undefined || value === 0) return 'flat';
  return value > 0 ? 'up' : 'down';
}
