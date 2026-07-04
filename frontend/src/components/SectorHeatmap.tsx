import { useEffect, useState } from 'react';
import Skeleton from './Skeleton';
import { fetchMarket, type MarketResponse } from '../api/client';
import { cachedFetch } from '../lib/dataCache';
import { directionClass } from '../lib/format';

// 등락률 크기 → 배경 틴트 알파(진하기). |pct| ≈ 3%에서 거의 최대.
function tintAlpha(changePct: number): number {
  const a = 0.1 + (Math.abs(changePct) / 3) * 0.62;
  return Math.min(0.72, a);
}

// 상승=빨강 계열 / 하락=파랑 계열(한국 관례). 진하기=등락 크기.
function tileTint(changePct: number): string {
  const alpha = tintAlpha(changePct);
  if (changePct > 0) return `rgba(255, 77, 79, ${alpha.toFixed(3)})`;
  if (changePct < 0) return `rgba(59, 130, 246, ${alpha.toFixed(3)})`;
  return 'transparent';
}

function formatSectorPct(changePct: number): string {
  const sign = changePct > 0 ? '+' : '';
  return `${sign}${changePct.toFixed(2)}%`;
}

export default function SectorHeatmap() {
  const [market, setMarket] = useState<MarketResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch('market', fetchMarket)
      .then((m) => {
        if (alive) setMarket(m);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const sectors = market?.sectors ?? [];
  const hasSectors = sectors.length > 0;

  // 정직성: fetch 실패 또는 빈 섹터 → placeholder(크래시 없음).
  if (failed || (market && !hasSectors)) {
    return (
      <aside
        className="sector-heatmap sector-heatmap--empty"
        data-testid="sector-heatmap"
        aria-label="섹터 히트맵"
      >
        <h3 className="sh-title">섹터 히트맵 · 시장폭</h3>
        <p className="sh-empty" data-testid="sector-heatmap-empty">
          시장 데이터 없음
        </p>
      </aside>
    );
  }

  if (!market) {
    return (
      <aside
        className="sector-heatmap"
        data-testid="sector-heatmap"
        aria-label="섹터 히트맵"
        aria-busy="true"
      >
        <h3 className="sh-title">섹터 히트맵 · 시장폭</h3>
        <Skeleton lines={2} />
      </aside>
    );
  }

  const { breadth } = market;
  const sorted = [...sectors].sort((a, b) => b.change_pct - a.change_pct);

  return (
    <aside
      className="sector-heatmap"
      data-testid="sector-heatmap"
      aria-label="섹터 히트맵"
    >
      <h3 className="sh-title">섹터 히트맵 · 시장폭</h3>

      <p className="sh-breadth" data-testid="market-breadth">
        <span className="dir-up">상승 {breadth.advancers}</span>
        {' / '}
        <span className="dir-down">하락 {breadth.decliners}</span>
        {' · '}
        <span className="sh-breadth-item">신고가 {breadth.new_highs}</span>
        {' · '}
        <span className="sh-breadth-item sh-limit">
          상한가 {breadth.limit_ups}
        </span>
      </p>

      <ul className="sh-tiles" data-testid="sector-tiles">
        {sorted.map((s) => {
          const dir = directionClass(s.change_pct);
          return (
            <li
              key={s.name}
              className="sh-tile"
              data-testid="sector-tile"
              data-dir={dir}
              style={{ backgroundColor: tileTint(s.change_pct) }}
            >
              <span className="sh-tile-name">{s.name}</span>
              <span className={`sh-tile-pct mono dir-${dir}`}>
                {formatSectorPct(s.change_pct)}
              </span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
