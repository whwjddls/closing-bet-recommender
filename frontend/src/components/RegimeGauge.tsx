import type { RegimeInfo } from '../api/client';

type Level = 'on' | 'half' | 'off';

// 초보자용 장 분위기 라벨: 1.0=🟢 좋음 / 0.5=🟡 보통(절반만) / 0.0=🔴 쉬어가기
const LEVEL_LABEL: Record<Level, string> = {
  on: '🟢 좋음',
  half: '🟡 보통',
  off: '🔴 쉬어가기',
};

function level(mult: number): Level {
  if (mult >= 1.0) return 'on';
  if (mult > 0) return 'half';
  return 'off';
}

export default function RegimeGauge({ regimes }: { regimes: RegimeInfo[] }) {
  return (
    <div className="regime-gauge" data-testid="regime-gauge">
      {regimes.map((r) => {
        const lv = level(r.regime_mult);
        return (
          <span
            key={r.market}
            data-testid={`regime-${r.market}`}
            data-level={lv}
            className={`regime-pill regime-${lv}`}
            title={`${r.market} 장 분위기 (베팅 비중 ${r.regime_mult.toFixed(1)}x)`}
          >
            <span className="regime-market">{r.market}</span>
            <span className="regime-label">{LEVEL_LABEL[lv]}</span>
            <span className="regime-mult">{r.regime_mult.toFixed(1)}x</span>
          </span>
        );
      })}
    </div>
  );
}
