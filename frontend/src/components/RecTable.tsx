import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Market, Recommendation } from '../api/client';
import { deriveBadges } from '../lib/badges';
import { formatPrice } from '../lib/format';
import MiniChart from './MiniChart';

type SortKey = 'score' | 'grade' | 'supply';
const GRADE_ORDER = { S: 0, A: 1, B: 2, C: 3 } as const;

export default function RecTable({
  recommendations,
}: {
  recommendations: Recommendation[];
}) {
  const [sortKey, setSortKey] = useState<SortKey>('score');
  const [marketFilter, setMarketFilter] = useState<'ALL' | Market>('ALL');
  const [supplyUpOnly, setSupplyUpOnly] = useState(false);

  const rows = useMemo(() => {
    let r = [...recommendations];
    if (marketFilter !== 'ALL') r = r.filter((x) => x.market === marketFilter);
    if (supplyUpOnly) r = r.filter((x) => x.supply_tilt > 1.0);
    r.sort((a, b) => {
      if (sortKey === 'grade')
        return GRADE_ORDER[a.grade] - GRADE_ORDER[b.grade];
      if (sortKey === 'supply') return b.supply_tilt - a.supply_tilt;
      return b.score - a.score;
    });
    return r;
  }, [recommendations, sortKey, marketFilter, supplyUpOnly]);

  return (
    <section>
      <div className="rec-controls">
        <select
          data-testid="sort-key"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
        >
          <option value="score">점수</option>
          <option value="grade">등급</option>
          <option value="supply">수급</option>
        </select>
        <select
          data-testid="filter-market"
          value={marketFilter}
          onChange={(e) => setMarketFilter(e.target.value as 'ALL' | Market)}
        >
          <option value="ALL">전체</option>
          <option value="KOSPI">KOSPI</option>
          <option value="KOSDAQ">KOSDAQ</option>
        </select>
        <label>
          <input
            data-testid="filter-supply-up"
            type="checkbox"
            checked={supplyUpOnly}
            onChange={(e) => setSupplyUpOnly(e.target.checked)}
          />
          수급+
        </label>
      </div>

      {rows.length === 0 ? (
        <p data-testid="rec-empty">표시할 추천 종목이 없습니다.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>★</th>
              <th>종목/코드</th>
              <th>현재가(잠정)</th>
              <th>매수가</th>
              <th>청산</th>
              <th>등급</th>
              <th>신호</th>
              <th>차트</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isTop3 = r.rank <= 3;
              return (
                <tr
                  key={r.ticker}
                  data-testid="rec-row"
                  data-top3={isTop3}
                  className={isTop3 ? 'rec-top3' : ''}
                >
                  <td>{isTop3 ? '★' : ''}</td>
                  <td>
                    <Link data-testid="rec-name" to={`/stock/${r.ticker}`}>
                      {r.name}
                    </Link>
                    <small> {r.ticker}</small>
                  </td>
                  <td>
                    {formatPrice(r.price_provisional)}
                    {r.provisional_flag && <sup title="잠정">*</sup>}
                  </td>
                  <td data-testid="buy-price">
                    {r.buy_price_final !== null
                      ? formatPrice(r.buy_price_final)
                      : `${formatPrice(r.buy_price_provisional)}*`}
                  </td>
                  <td data-testid="exit-cta" className="exit-cta">
                    <strong className="exit-primary">{r.exit_label}</strong>
                    <div className="ref-stop">
                      목 {formatPrice(r.target_price)} / 손{' '}
                      {formatPrice(r.stop_price)} (보유 시)
                    </div>
                  </td>
                  <td
                    data-testid="rec-grade"
                    className={`grade grade-${r.grade}`}
                  >
                    {r.grade}
                  </td>
                  <td>
                    {deriveBadges(r).map((b) => (
                      <span key={b.key} className={`badge badge-${b.key}`}>
                        {b.label}
                      </span>
                    ))}
                  </td>
                  <td>
                    <MiniChart data={r.spark} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}
