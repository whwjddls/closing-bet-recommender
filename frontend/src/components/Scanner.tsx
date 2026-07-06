import { useMemo, useState } from 'react';
import type { Market, UniverseRow } from '../api/client';

type ScanSort = 'value' | 'market';
const MARKET_ORDER: Record<string, number> = { KOSPI: 0, KOSDAQ: 1 };

// 20일 평균 거래대금을 억 단위로 표기(정렬·가독). 결측이면 —.
function formatValueEok(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const eok = value / 1e8;
  return `${eok.toLocaleString('ko-KR', {
    maximumFractionDigits: eok >= 10 ? 0 : 1,
  })}억`;
}

// null-safe 내림차순(결측은 항상 뒤로).
function byValueDesc(a: UniverseRow, b: UniverseRow): number {
  return (b.avg_value_20d ?? -Infinity) - (a.avg_value_20d ?? -Infinity);
}

// 쉬어가는 날 후보 목록(참고용). D-1 거래대금 상위 200.
// 적격(관리·경고·투자주의 제외) 판정은 장전 프리페치(pykrx)엔 재료가 없어 못 하고,
// 15:20 스캔에서 KIS 실시간 플래그로 이뤄진다 — 그래서 여기선 판정을 표시하지 않는다.
export default function Scanner({
  rows,
  asOf = null,
}: {
  rows: UniverseRow[];
  asOf?: string | null;
}) {
  const [sortKey, setSortKey] = useState<ScanSort>('value');

  const total = rows.length;

  const visible = useMemo(() => {
    return [...rows].sort((a, b) => {
      if (sortKey === 'market') {
        const m =
          (MARKET_ORDER[a.market as Market] ?? 9) -
          (MARKET_ORDER[b.market as Market] ?? 9);
        if (m !== 0) return m;
        return byValueDesc(a, b);
      }
      return byValueDesc(a, b);
    });
  }, [rows, sortKey]);

  // 장전 프리페치 전(유니버스 미적재)이면 정직한 안내.
  if (total === 0) {
    return (
      <p data-testid="scan-empty" className="scan-empty">
        스캔 풀 데이터가 없습니다 — 장전 프리페치 전입니다.
      </p>
    );
  }

  return (
    <section className="scanner-wrap" data-testid="scanner">
      <div className="scanner-head">
        <span className="scan-count" data-testid="scan-count">
          스캔 유니버스 <strong>{total}</strong>종목
        </span>
        <div className="scanner-controls">
          <select
            data-testid="scan-sort"
            value={sortKey}
            onChange={(e) => setSortKey(e.target.value as ScanSort)}
            aria-label="스캐너 정렬"
          >
            <option value="value">거래대금순</option>
            <option value="market">시장순</option>
          </select>
        </div>
      </div>

      <table className="scanner">
        <caption data-testid="scan-as-of">스캔 기준일 {asOf ?? '-'}</caption>
        <thead>
          <tr>
            <th>종목</th>
            <th>시장</th>
            <th className="num">20일 평균 거래대금</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((r) => (
            <tr key={r.ticker} data-testid="scan-row">
              <td className="scan-name-cell">
                {r.name && <span className="scan-name">{r.name}</span>}
                <small>{r.ticker}</small>
              </td>
              <td className="scan-market">{r.market}</td>
              <td className="num scan-value">{formatValueEok(r.avg_value_20d)}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="scan-note" data-testid="scan-note">
        거래대금 상위 200 후보 · 실제 적격 판정(관리·경고·투자주의 제외)은 15:20
        스캔에서 이뤄져요.
      </p>
    </section>
  );
}
