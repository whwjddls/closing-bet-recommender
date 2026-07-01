import { useEffect, useState } from 'react';
import { fetchMarket, type MarketInvestors as Investors } from '../api/client';
import { directionClass } from '../lib/format';

// 순매수(억) 표기: 방향 화살표 + 부호 + 절대값 억 단위(천단위 콤마).
// 한국 관례색: 순매수(+)=상승빨강, 순매도(−)=하락파랑.
function formatNet(net: number): string {
  const dir = directionClass(net);
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '·';
  const sign = net > 0 ? '+' : net < 0 ? '−' : '';
  const magnitude = Math.abs(net).toLocaleString('ko-KR');
  return `${arrow} ${sign}${magnitude}억`;
}

const ROWS: { key: keyof Investors; label: string }[] = [
  { key: 'foreign_net', label: '외국인' },
  { key: 'institution_net', label: '기관' },
  { key: 'individual_net', label: '개인' },
];

export default function MarketInvestors() {
  const [investors, setInvestors] = useState<Investors | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchMarket()
      .then((m) => {
        if (!alive) return;
        // 구버전 응답(investors 미포함)은 정직하게 placeholder 처리.
        if (m.investors) setInvestors(m.investors);
        else setFailed(true);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (failed) {
    return (
      <aside
        className="market-investors market-investors--empty"
        data-testid="market-investors"
        aria-label="투자자별 수급"
      >
        <h3 className="mi-title">투자자별 수급 · D-1</h3>
        <p className="mi-empty" data-testid="market-investors-empty">
          수급 데이터 없음
        </p>
      </aside>
    );
  }

  if (!investors) {
    return (
      <aside
        className="market-investors"
        data-testid="market-investors"
        aria-label="투자자별 수급"
        aria-busy="true"
      >
        <h3 className="mi-title">투자자별 수급 · D-1</h3>
        <p className="mi-loading">로딩 중…</p>
      </aside>
    );
  }

  return (
    <aside
      className="market-investors"
      data-testid="market-investors"
      aria-label="투자자별 수급"
    >
      <h3 className="mi-title">
        투자자별 수급 <span className="mi-scope">· D-1 확정 순매수</span>
      </h3>
      <ul className="mi-rows" data-testid="investor-rows">
        {ROWS.map(({ key, label }) => {
          const net = investors[key];
          const dir = directionClass(net);
          return (
            <li
              key={key}
              className="mi-row"
              data-testid={`investor-${key}`}
              data-dir={dir}
            >
              <span className="mi-label">{label}</span>
              <span className={`mi-net mono dir-${dir}`}>
                {formatNet(net)}
              </span>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
