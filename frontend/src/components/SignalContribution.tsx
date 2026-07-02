import type { StockContributions } from '../api/client';

interface Props {
  contributions: StockContributions;
  final: number;
}

// 5개 승수(곱셈 사슬 입력)를 1.0 기준으로 시각화. >1 부스트(상승빨강)/<1 드래그(하락파랑).
// 초보자용 라벨: 신호 5가지 = 신고가·거래량·장분위기·수급·재료(veto 게이트).
const MULT_BARS: { key: string; label: string; full: string }[] = [
  { key: 's_shin', label: '신고가', full: 's_shin' },
  { key: 'rvol_confirm', label: '거래량', full: 'rvol_confirm' },
  { key: 'regime_mult', label: '장분위기', full: 'regime_mult' },
  { key: 'supply_tilt', label: '수급', full: 'supply_tilt' },
  { key: 'veto', label: '재료', full: 'veto' },
];

// 승수(0~2 가정)를 막대 폭 %로. 1.0=중앙. clamp 로 벗어난 값 방어.
function multiplierWidth(value: number): number {
  const clamped = Math.max(0, Math.min(2, value));
  return (clamped / 2) * 100;
}

// core 곱셈 사슬을 신호별로 분해해 표기(veto는 0/1 게이트라 정수 표기).
export default function SignalContribution({ contributions, final }: Props) {
  const { s_shin, rvol_confirm, supply_tilt, regime_mult, veto, core } =
    contributions;
  const byKey: Record<string, number> = {
    s_shin,
    rvol_confirm,
    supply_tilt,
    regime_mult,
    veto,
  };
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
    <div className="signal-panel">
      {/* 신호 5가지 막대 — 1.0 기준 부스트/드래그 시각화 */}
      <p className="signal-legend">
        신호 5가지: 신고가 · 거래량 · 장분위기 · 수급 · 재료
      </p>
      <div
        className="mult-bars"
        data-testid="mult-bars"
        aria-label="신호 5가지"
      >
        {MULT_BARS.map(({ key, label, full }) => {
          const value = byKey[key];
          const dir = value > 1 ? 'up' : value < 1 ? 'down' : 'flat';
          const isGate = key === 'veto';
          return (
            <div
              key={key}
              className="mult-bar-row"
              data-testid={`mult-bar-${key}`}
              data-dir={dir}
              title={`${full} = ${isGate ? value : value.toFixed(2)}`}
            >
              <span className="mult-bar-label">{label}</span>
              <span className="mult-bar-track">
                <span className="mult-bar-mid" />
                <span
                  className={`mult-bar-fill dir-bg-${dir}`}
                  style={{ width: `${multiplierWidth(value)}%` }}
                />
              </span>
              <span className="mult-bar-val mono">
                {isGate ? (value ? '통과' : '차단') : value.toFixed(2)}
              </span>
            </div>
          );
        })}
      </div>

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
    </div>
  );
}
