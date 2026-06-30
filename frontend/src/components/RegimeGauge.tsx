import type { RegimeInfo } from '../api/client';

type Level = 'on' | 'half' | 'off';

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
          >
            <span className="regime-market">{r.market}</span>
            <span className="regime-mult">{r.regime_mult.toFixed(1)}</span>
          </span>
        );
      })}
    </div>
  );
}
