import type { RegimeInfo } from '../api/client';
import { formatPrice } from '../lib/format';

type Level = 'on' | 'half' | 'off';

// regime_mult → 초보자용 장 분위기 신호등. 게이지·헤더 판정과 동일 규칙.
// 1.0=좋음(go) / 0.5=보통·절반만(hold) / 0.0=쉬어가기(off) — 색은 mood-dot 원이 담당.
function regimeBadge(mult: number): { level: Level; label: string } {
  if (mult >= 1.0) return { level: 'on', label: '좋음' };
  if (mult > 0) return { level: 'half', label: '보통' };
  return { level: 'off', label: '쉬어가기' };
}

// GlobalHeader 바로 아래 상시 노출되는 얇은 지수 바.
// /recommendations 의 regimes 만 사용(신규 API 없음).
export default function IndexStrip({ regimes }: { regimes: RegimeInfo[] }) {
  if (regimes.length === 0) {
    return (
      <div className="index-strip" data-testid="index-strip" role="status">
        <span className="idx-empty" data-testid="index-strip-empty">
          시황 데이터 없음
        </span>
      </div>
    );
  }

  return (
    <div className="index-strip" data-testid="index-strip" role="status">
      {regimes.map((r) => {
        const above = r.index_level >= r.ma5; // 5일선 위/아래(관례: 위=상승 빨강)
        const badge = regimeBadge(r.regime_mult);
        return (
          <div
            key={r.market}
            className="idx-item"
            data-testid={`index-strip-${r.market}`}
          >
            <span className="idx-market">{r.market}</span>
            <span className="idx-level num">{formatPrice(r.index_level)}</span>
            <span
              className={`idx-ma ${above ? 'dir-up' : 'dir-down'}`}
              data-testid={`index-ma-${r.market}`}
            >
              {above ? '5MA 위' : '5MA 아래'}
            </span>
            <span
              className={`idx-regime regime-${badge.level}`}
              data-testid={`index-regime-${r.market}`}
              data-level={badge.level}
            >
              <span className="mood-dot" data-mood={badge.level} aria-hidden="true" />
              {badge.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}
