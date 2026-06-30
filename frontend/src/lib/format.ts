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
