import type { Candle } from '../api/client';
import { directionClass } from '../lib/format';

interface Props {
  candles: Candle[];
}

// 거래대금(≈ 종가×거래량) 히스토그램 — 일봉 차트 하단에 붙는 막대.
// 봉의 방향(종가≥시가=상승빨강/하락파랑)으로 막대 색을 맞춘다.
export default function VolumeHistogram({ candles }: Props) {
  if (candles.length === 0) {
    return (
      <div
        className="volume-histogram volume-histogram--empty"
        data-testid="volume-histogram"
      >
        <span className="vh-title">거래대금</span>
        <p className="vh-empty" data-testid="volume-histogram-empty">
          거래 데이터 없음
        </p>
      </div>
    );
  }

  // 거래대금 근사: 종가 × 거래량.
  const values = candles.map((c) => c.close * c.volume);
  const max = Math.max(...values, 1);

  return (
    <div className="volume-histogram" data-testid="volume-histogram">
      <span className="vh-title">거래대금 (종가×거래량 근사)</span>
      <ol className="vh-bars" aria-label="일별 거래대금">
        {candles.map((c, i) => {
          const dir = directionClass(c.close - c.open);
          const heightPct = (values[i] / max) * 100;
          return (
            <li
              key={c.date}
              className="vh-bar-cell"
              data-testid="volume-bar"
              title={`${c.date} · 거래대금 ${Math.round(values[i]).toLocaleString('ko-KR')}`}
            >
              <span
                className={`vh-bar dir-bg-${dir}`}
                style={{ height: `${Math.max(heightPct, 2)}%` }}
              />
            </li>
          );
        })}
      </ol>
    </div>
  );
}
