import type { StockContributions } from '../api/client';

interface Props {
  contributions: StockContributions;
  final: number;
}

// core 곱셈 사슬을 신호별로 분해해 표기(veto는 0/1 게이트라 정수 표기).
export default function SignalContribution({ contributions, final }: Props) {
  const { s_shin, rvol_confirm, supply_tilt, regime_mult, veto, core } =
    contributions;
  const items: [string, string, number][] = [
    ['s_shin', 's_신', s_shin],
    ['rvol_confirm', 'rvol_confirm', rvol_confirm],
    ['supply_tilt', 'supply_tilt', supply_tilt],
    ['regime_mult', 'regime', regime_mult],
    ['veto', 'veto', veto],
    ['core', 'core', core],
    ['final', 'final', final],
  ];
  return (
    <dl className="signal-contribution">
      {items.map(([key, label, value]) => (
        <div
          key={key}
          data-testid={`contrib-${key}`}
          className="contrib-row"
        >
          <dt>{label}</dt>
          <dd>{key === 'veto' ? value : value.toFixed(2)}</dd>
        </div>
      ))}
    </dl>
  );
}
