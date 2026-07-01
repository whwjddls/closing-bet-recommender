import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Market, Recommendation } from '../api/client';
import { deriveBadges } from '../lib/badges';
import { formatPrice, formatPercent, directionClass } from '../lib/format';
import MiniChart from './MiniChart';

type SortKey = 'score' | 'grade' | 'supply';
const GRADE_ORDER = { S: 0, A: 1, B: 2, C: 3 } as const;

// 목표가 기준 기대수익률(청산=오전VWAP 전, 목표 도달 시 상단). buy_price_final 우선.
function expectedReturn(r: Recommendation): number | null {
  const basis = r.buy_price_final ?? r.buy_price_provisional;
  if (!basis) return null;
  return (r.target_price - basis) / basis;
}

function hasRisk(r: Recommendation): boolean {
  return r.veto < 1;
}

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

  const top3 = useMemo(
    () => [...rows].filter((r) => r.rank <= 3).sort((a, b) => a.rank - b.rank),
    [rows],
  );

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

      {top3.length > 0 && (
        <div className="rec-top3-cards" data-testid="top3-cards">
          {top3.map((r) => {
            const exp = expectedReturn(r);
            return (
              <article
                key={r.ticker}
                data-testid="top3-card"
                className={`top3-card grade-row-${r.grade}`}
              >
                <div className="t3-head">
                  <span className={`grade-badge grade-${r.grade}`}>
                    {r.grade}
                  </span>
                  <Link className="t3-name" to={`/stock/${r.ticker}`}>
                    {r.name}
                  </Link>
                  <span className="t3-code">{r.ticker}</span>
                  <span className="t3-rank">#{r.rank}</span>
                </div>
                <div className="t3-row">
                  <span>매수</span>
                  <span className="t3-val">
                    {formatPrice(r.buy_price_final ?? r.buy_price_provisional)}
                    {r.provisional_flag && (
                      <span className="prov-mark" title="잠정 15:20">
                        *
                      </span>
                    )}
                  </span>
                </div>
                <div className="t3-row">
                  <span>청산</span>
                  <span className="t3-val">{r.exit_label}</span>
                </div>
                <div className="t3-row t3-exp">
                  <span>기대</span>
                  <span className={`t3-val dir-${directionClass(exp)}`}>
                    {formatPercent(exp)}
                  </span>
                </div>
                {hasRisk(r) && <div className="t3-risk">⚠ 리스크 플래그</div>}
              </article>
            );
          })}
        </div>
      )}

      {rows.length === 0 ? (
        <p data-testid="rec-empty">표시할 추천 종목이 없습니다.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th className="col-risk">⚑</th>
              <th className="col-star">★</th>
              <th>종목/코드</th>
              <th>현재가(잠정)</th>
              <th>매수가</th>
              <th>청산</th>
              <th>기대</th>
              <th>등급</th>
              <th>신호</th>
              <th>차트</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const isTop3 = r.rank <= 3;
              const risk = hasRisk(r);
              const exp = expectedReturn(r);
              const rowClass = [
                isTop3 ? 'rec-top3' : '',
                `grade-row-${r.grade}`,
              ]
                .filter(Boolean)
                .join(' ');
              return (
                <tr
                  key={r.ticker}
                  data-testid="rec-row"
                  data-top3={isTop3}
                  data-risk={risk}
                  className={rowClass}
                >
                  <td
                    className={`col-risk${risk ? ' has-risk' : ''}`}
                    title={risk ? '리스크: 희석 veto' : '리스크 없음'}
                  >
                    {risk ? '⚠' : '─'}
                  </td>
                  <td className="col-star">{isTop3 ? '★' : ''}</td>
                  <td>
                    <Link data-testid="rec-name" to={`/stock/${r.ticker}`}>
                      {r.name}
                    </Link>
                    <small> {r.ticker}</small>
                  </td>
                  <td className="num">
                    {formatPrice(r.price_provisional)}
                    {r.provisional_flag && (
                      <sup className="prov-mark" title="잠정 15:20">
                        *
                      </sup>
                    )}
                  </td>
                  <td data-testid="buy-price" className="num">
                    {r.buy_price_final !== null ? (
                      formatPrice(r.buy_price_final)
                    ) : (
                      <>
                        {formatPrice(r.buy_price_provisional)}
                        <span className="prov-mark">*</span>
                      </>
                    )}
                  </td>
                  <td data-testid="exit-cta" className="exit-cta">
                    <strong className="exit-primary">{r.exit_label}</strong>
                    <div className="ref-stop">
                      목 {formatPrice(r.target_price)} / 손{' '}
                      {formatPrice(r.stop_price)} (보유 시)
                    </div>
                  </td>
                  <td
                    data-testid="exp-return"
                    className={`exp-return dir-${directionClass(exp)}`}
                  >
                    {formatPercent(exp)}
                  </td>
                  <td
                    data-testid="rec-grade"
                    className={`grade grade-${r.grade}`}
                  >
                    <span>{r.grade}</span>
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
