import { useMemo, useState } from 'react';
import { Search, Star } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Market, Recommendation } from '../api/client';
import { deriveBadges } from '../lib/badges';
import { formatPrice, formatPercent, directionClass } from '../lib/format';
import { formatSupplyToday } from '../lib/supplyLabel';
import InfoDot from './InfoDot';
import NewsBadge from './NewsBadge';

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

// supply_today("외인▲기관▲") 라벨의 방향색 — +만 존재하면 상승색.
function supplyDir(label: string): 'up' | 'flat' {
  return label.includes('+') ? 'up' : 'flat';
}

export default function RecTable({
  recommendations,
  pickedTickers,
  onTogglePick,
}: {
  recommendations: Recommendation[];
  pickedTickers?: Set<string>;
  onTogglePick?: (ticker: string) => void;
}) {
  const showPick = typeof onTogglePick === 'function';
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

  const colCount = showPick ? 10 : 9;

  return (
    <section>
      <div className="rec-controls">
        <select
          data-testid="sort-key"
          value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}
        >
          <option value="score">종합 점수순</option>
          <option value="grade">등급순</option>
          <option value="supply">수급 세기순</option>
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
          수급 좋은 것만
        </label>
      </div>

      {rows.length === 0 ? (
        <p data-testid="rec-empty">
          조건에 맞는 종목이 없어요. 필터를 풀어보세요.
        </p>
      ) : (
        <>
          <p className="rec-material-hint" data-testid="material-hint">
            <Search size={13} aria-hidden="true" /> 매수 전 마지막 체크:{' '}
            <strong>오늘 재료(주도 테마·뉴스)가 있는 종목인지</strong> 종목명을
            눌러 최근 뉴스로 확인하세요 — 숫자 필터는 재료를 판단하지 못해요.
          </p>
          <table className="rec-table">
            <thead>
              <tr>
                <th className="col-num">#</th>
                <th>등급</th>
                <th>종목</th>
                <th className="num">
                  현재가
                  <InfoDot
                    label="15:20 기준"
                    text="현재가·매수 참고가·예상 마감가 모두 15:20 기준 잠정값이에요. 마감(15:30)에 확정 — 아직 확정 아님"
                  />
                </th>
                <th className="num">
                  참고 목표
                  <InfoDot
                    label="참고 목표"
                    text="목표가 도달 시 기대수익률을 함께 표시. 기본 전략은 아침에 파는 거예요"
                  />
                </th>
                <th className="num">참고 손절</th>
                <th className="num">
                  평소보다 거래
                  <InfoDot
                    label="평소보다 거래"
                    text="평소보다 오늘 거래가 몇 배인지. 3배↑면 관심이 몰린 거예요"
                  />
                </th>
                <th>
                  수급
                  <InfoDot
                    label="당일 수급"
                    text="오늘 잠정 외국인·기관 흐름(확정 전 — 어제 확정 수급과 다름)"
                  />
                </th>
                <th>
                  재료
                  <InfoDot
                    align="right"
                    label="재료 확인"
                    text="숫자 필터는 재료(주도 테마·뉴스)를 판단하지 못해요. 매수 전 직접 확인하세요"
                  />
                </th>
                {showPick && <th className="col-pick">담기</th>}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => {
                const isTop3 = r.rank <= 3;
                const risk = hasRisk(r);
                const exp = expectedReturn(r);
                const supplyLabel = formatSupplyToday(r.supply_today);
                const rowClass = [isTop3 ? 'rec-top3' : '', `grade-row-${r.grade}`]
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
                    <td className="col-num mono">
                      {isTop3 && (
                        <Star
                          size={11}
                          data-testid="row-rank-marker"
                          className="rank-star"
                          aria-hidden="true"
                        />
                      )}
                      {r.rank}
                    </td>
                    <td
                      data-testid="rec-grade"
                      className={`grade grade-${r.grade}`}
                    >
                      <span>{r.grade}</span>
                    </td>
                    <td className="rec-name-cell">
                      <div className="rec-name-line">
                        <Link data-testid="rec-name" to={`/stock/${r.ticker}`}>
                          {r.name}
                        </Link>
                        <small> {r.ticker}</small>
                      </div>
                      <div className="rec-badges">
                        {deriveBadges(r).map((b) => (
                          <span key={b.key} className={`badge badge-${b.key}`}>
                            {b.label}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td className="num rec-price-cell">
                      <span className="rec-px">
                        {formatPrice(r.price_provisional)}
                        {r.provisional_flag && (
                          <sup className="prov-mark" title="15:20 기준(확정 전)">
                            *
                          </sup>
                        )}
                      </span>
                      <span data-testid="buy-price" className="rec-buy">
                        매수{' '}
                        {r.buy_price_final !== null ? (
                          formatPrice(r.buy_price_final)
                        ) : (
                          <>
                            {formatPrice(r.buy_price_provisional)}
                            <span className="prov-mark">*</span>
                          </>
                        )}
                      </span>
                      <span data-testid="exp-close" className="rec-exp">
                        예상{' '}
                        {r.exp_close != null ? (
                          <span title="15:20 예상 체결가">
                            {formatPrice(r.exp_close)}
                          </span>
                        ) : (
                          '—'
                        )}
                      </span>
                    </td>
                    <td className="num rec-target-cell">
                      <span className="rec-target">
                        {formatPrice(r.target_price)}
                      </span>
                      <span
                        data-testid="exp-return"
                        className={`exp-return dir-${directionClass(exp)}`}
                      >
                        {formatPercent(exp)}
                      </span>
                    </td>
                    <td className="num">{formatPrice(r.stop_price)}</td>
                    <td className={`num rvol-cell dir-${directionClass((r.rvol ?? 0) - 1)}`}>
                      {r.rvol != null ? `${r.rvol.toFixed(1)}배` : '—'}
                    </td>
                    <td data-testid="supply-cell" className="supply-cell">
                      {r.supply_today ? (
                        <span
                          data-testid="supply-today-badge"
                          className={`badge badge-supply-today dir-${supplyDir(
                            supplyLabel,
                          )}`}
                          title="오늘 잠정 외국인·기관 흐름 (확정 전 — 어제 확정 수급과 다름)"
                        >
                          {supplyLabel}
                          <span className="badge-prov-tag">잠정</span>
                        </span>
                      ) : (
                        <span className="supply-dash">—</span>
                      )}
                    </td>
                    <td className="material-cell">
                      <NewsBadge ticker={r.ticker} />
                    </td>
                    {showPick && (
                      <td className="col-pick">
                        {(() => {
                          const isPicked =
                            pickedTickers?.has(r.ticker) ?? false;
                          return (
                            <button
                              type="button"
                              data-testid="pick-toggle"
                              data-picked={isPicked}
                              className={`pick-btn${isPicked ? ' picked' : ''}`}
                              aria-pressed={isPicked}
                              aria-label={`${r.name} ${
                                isPicked ? '빼기' : '담기'
                              }`}
                              onClick={() => onTogglePick?.(r.ticker)}
                            >
                              {isPicked ? '담음' : '담기'}
                            </button>
                          );
                        })()}
                      </td>
                    )}
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <td
                  data-testid="table-footnote"
                  className="table-footnote"
                  colSpan={colCount}
                >
                  * 15:20 잠정 — 마감(15:30) 확정 · 기본 전략: 다음날 아침
                  9~10시에 팔기 · 참고 손절은 계속 들고 갈 때만
                </td>
              </tr>
            </tfoot>
          </table>
        </>
      )}
    </section>
  );
}
