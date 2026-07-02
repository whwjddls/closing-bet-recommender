const W = 240;
const H = 56;
const PAD = 2;

interface Props {
  strategy: number[];
  benchmark?: number[]; // 코스피 벤치마크(비어있으면 오버레이 생략)
}

function toPoints(data: number[], min: number, span: number): string {
  if (data.length < 2) return '';
  return data
    .map((v, i) => {
      const x = PAD + (i / (data.length - 1)) * (W - PAD * 2);
      const y = H - PAD - ((v - min) / span) * (H - PAD * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

// 전략 누적곡선 + (선택) 코스피 벤치마크 회색 오버레이.
// 두 곡선을 공통 스케일로 정규화해 상대 성과를 비교할 수 있게 한다.
export default function CumulativeCurve({ strategy, benchmark }: Props) {
  const hasBench = !!benchmark && benchmark.length >= 2;
  const all = hasBench ? [...strategy, ...benchmark] : strategy;

  if (strategy.length < 2) {
    return (
      <div
        data-testid="cum-chart"
        data-empty="true"
        className="cum-chart cum-empty"
        style={{ width: W, height: H }}
      >
        아직 그릴 기록이 없어요
      </div>
    );
  }

  const min = Math.min(...all);
  const max = Math.max(...all);
  const span = max - min || 1;
  const trend = strategy[strategy.length - 1] >= strategy[0] ? 'up' : 'down';

  return (
    <svg
      data-testid="cum-chart"
      data-trend={trend}
      data-has-benchmark={hasBench}
      width={W}
      height={H}
      className={`cum-chart cum-${trend}`}
      role="img"
      aria-label="누적 수익곡선"
    >
      {/* 0선(기준) */}
      {min < 0 && max > 0 && (
        <line
          className="cum-zero"
          x1={PAD}
          x2={W - PAD}
          y1={H - PAD - ((0 - min) / span) * (H - PAD * 2)}
          y2={H - PAD - ((0 - min) / span) * (H - PAD * 2)}
        />
      )}
      {hasBench && (
        <polyline
          data-testid="benchmark-line"
          className="cum-benchmark"
          points={toPoints(benchmark!, min, span)}
          fill="none"
          strokeWidth={1.25}
        />
      )}
      <polyline
        className="cum-strategy"
        points={toPoints(strategy, min, span)}
        fill="none"
        strokeWidth={1.75}
      />
    </svg>
  );
}
