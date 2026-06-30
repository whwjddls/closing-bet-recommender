const W = 80;
const H = 24;

export default function MiniChart({ data }: { data?: number[] | null }) {
  if (!data || data.length < 2) {
    return (
      <svg data-testid="mini-chart" data-empty="true" width={W} height={H} />
    );
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const span = max - min || 1;
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * W;
      const y = H - ((v - min) / span) * H;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const trend = data[data.length - 1] >= data[0] ? 'up' : 'down';
  return (
    <svg
      data-testid="mini-chart"
      data-trend={trend}
      width={W}
      height={H}
      className={`mini mini-${trend}`}
    >
      <polyline points={points} fill="none" strokeWidth={1.5} />
    </svg>
  );
}
