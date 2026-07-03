import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Market, Recommendation } from '../api/client';
import { deriveBadges } from '../lib/badges';
import { formatPrice, formatPercent, directionClass } from '../lib/format';
import MiniChart from './MiniChart';
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
                  <span>매수 참고가</span>
                  <span className="t3-val">
                    {formatPrice(r.buy_price_final ?? r.buy_price_provisional)}
                    {r.provisional_flag && (
                      <span className="prov-mark" title="15:20 기준(확정 전)">
                        *
                      </span>
                    )}
                  </span>
                </div>
                <div className="t3-row">
                  <span>아침 팔기</span>
                  <span className="t3-val">{r.exit_label}</span>
                </div>
                <div className="t3-row t3-exp">
                  <span>기대 수익</span>
                  <span className={`t3-val dir-${directionClass(exp)}`}>
                    {formatPercent(exp)}
                  </span>
                </div>
                <div className="t3-row t3-news">
                  <span>
                    재료
                    <InfoDot
                      label="재료 확인"
                      text="숫자 필터는 재료(주도 테마·뉴스)를 판단하지 못해요. 매수 전 직접 확인하세요"
                    />
                  </span>
                  <span className="t3-val">
                    <NewsBadge ticker={r.ticker} />
                  </span>
                </div>
                {hasRisk(r) && <div className="t3-risk">⚠ 조심 신호</div>}
              </article>
            );
          })}
        </div>
      )}

      {rows.length === 0 ? (
        <p data-testid="rec-empty">
          조건에 맞는 종목이 없어요. 필터를 풀어보세요.
        </p>
      ) : (
        <>
          <p className="rec-material-hint" data-testid="material-hint">
            🔍 매수 전 마지막 체크:{' '}
            <strong>오늘 재료(주도 테마·뉴스)가 있는 종목인지</strong> 종목명을
            눌러 최근 뉴스로 확인하세요 — 숫자 필터는 재료를 판단하지 못해요.
          </p>
          <table>
          <thead>
            <tr>
              <th className="col-risk">⚑</th>
              <th className="col-star">★</th>
              <th>종목</th>
              <th>
                현재가
                <InfoDot
                  label="15:20 기준"
                  text="15:20 기준 값이에요. 마감(15:30) 때 조금 바뀔 수 있어요 — 아직 확정 아님"
                />
              </th>
              <th>
                매수 참고가
                <InfoDot
                  label="매수 참고가"
                  text="15:20 기준 매수 참고가. 실제 체결가는 다를 수 있어요"
                />
              </th>
              <th className="col-exp-close">
                예상 마감가
                <InfoDot
                  label="예상 마감가"
                  text="15:20에 계산한 예상 마감가예요. 마감(15:30)에 확정 — 아직 잠정값"
                />
              </th>
              <th>
                다음날 아침 팔기
                <InfoDot
                  label="아침 팔기"
                  text="기본 전략은 다음날 아침 9~10시에 파는 거예요(그 시간대 평균가 기준)"
                />
              </th>
              <th>기대</th>
              <th>
                종합 점수
                <InfoDot
                  label="등급"
                  text="S=다섯 신호(신고가·거래량·장분위기·수급·재료)가 모두 강함. 확신 최상"
                />
              </th>
              <th>
                신호
                <InfoDot
                  align="right"
                  label="평소보다 거래"
                  text="평소보다 오늘 거래가 몇 배인지. 3배↑면 관심이 몰린 거예요"
                />
              </th>
              <th>차트</th>
              {showPick && <th className="col-pick">담기</th>}
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
                    title={
                      risk
                        ? '조심 신호: 증자·CB 등 물량이 늘 수 있는 공시'
                        : '특이사항 없음'
                    }
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
                      <sup className="prov-mark" title="15:20 기준(확정 전)">
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
                  <td
                    data-testid="exp-close"
                    className="num col-exp-close exp-close-cell"
                  >
                    {r.exp_close != null ? (
                      <span
                        className="exp-close-val"
                        title="15:20 예상 체결가"
                      >
                        {formatPrice(r.exp_close)}
                      </span>
                    ) : (
                      <span
                        className="exp-close-dash"
                        aria-label="예상 체결가 없음"
                      >
                        —
                      </span>
                    )}
                  </td>
                  <td data-testid="exit-cta" className="exit-cta">
                    <strong className="exit-primary">{r.exit_label}</strong>
                    <div className="ref-stop">
                      참고 목표 {formatPrice(r.target_price)} / 참고 손절{' '}
                      {formatPrice(r.stop_price)} (계속 들고 갈 때)
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
                    {r.supply_today && (
                      <span
                        data-testid="supply-today-badge"
                        className="badge badge-supply-today"
                        title="오늘 잠정 외국인·기관 흐름 (확정 전 — 어제 확정 수급과 다름)"
                      >
                        {r.supply_today}
                        <span className="badge-prov-tag">잠정</span>
                      </span>
                    )}
                    {deriveBadges(r).map((b) => (
                      <span key={b.key} className={`badge badge-${b.key}`}>
                        {b.label}
                      </span>
                    ))}
                  </td>
                  <td>
                    <MiniChart data={r.spark} />
                  </td>
                  {showPick && (
                    <td className="col-pick">
                      {(() => {
                        const isPicked = pickedTickers?.has(r.ticker) ?? false;
                        return (
                          <button
                            type="button"
                            data-testid="pick-toggle"
                            data-picked={isPicked}
                            className={`pick-btn${isPicked ? ' picked' : ''}`}
                            aria-pressed={isPicked}
                            aria-label={`${r.name} ${isPicked ? '빼기' : '담기'}`}
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
          </table>
        </>
      )}
    </section>
  );
}
