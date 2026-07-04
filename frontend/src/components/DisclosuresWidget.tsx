import { useEffect, useState } from 'react';
import Skeleton from './Skeleton';
import {
  fetchDisclosures,
  type DisclosuresResponse,
  type DisclosureItem,
} from '../api/client';
import { cachedFetch } from '../lib/dataCache';

// 희석성(주식수 증가) 공시는 리스크 적색 톤. 배당류는 중립/청색.
// 백엔드 kind enum 미확정 → 토큰 매칭으로 분류(기본=희석 아님).
const DILUTIVE_TOKENS = [
  '증자',
  '유상',
  'cb',
  '전환사채',
  'bw',
  '신주인수권',
  '워런트',
  'dilut',
  '오버행',
];

function isDilutive(kind: string): boolean {
  const k = kind.toLowerCase();
  return DILUTIVE_TOKENS.some((t) => k.includes(t));
}

function kindClass(kind: string): string {
  return isDilutive(kind) ? 'dsc-kind--dilution' : 'dsc-kind--neutral';
}

// (ticker,title) 기준 중복 제거 — 정정 재공시가 같은 제목으로 두 번 뜨는 것 방지.
function dedupeDisclosures(items: DisclosureItem[]): DisclosureItem[] {
  const seen = new Set<string>();
  const unique: DisclosureItem[] = [];
  for (const item of items) {
    const key = `${item.ticker}::${item.title}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(item);
  }
  return unique;
}

export default function DisclosuresWidget() {
  const [data, setData] = useState<DisclosuresResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch('disclosures', fetchDisclosures)
      .then((d) => {
        if (alive) setData(d);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const items: DisclosureItem[] = dedupeDisclosures(data?.items ?? []);
  const hasItems = items.length > 0;

  if (failed || (data && !hasItems)) {
    return (
      <aside
        className="disclosures-widget disclosures-widget--empty"
        data-testid="disclosures-widget"
        aria-label="공시 일정"
      >
        <h3 className="dsc-title">공시 일정</h3>
        <p className="dsc-empty" data-testid="disclosures-widget-empty">
          공시 데이터 없음
        </p>
      </aside>
    );
  }

  if (!data) {
    return (
      <aside
        className="disclosures-widget"
        data-testid="disclosures-widget"
        aria-label="공시 일정"
        aria-busy="true"
      >
        <h3 className="dsc-title">공시 일정</h3>
        <Skeleton lines={3} />
      </aside>
    );
  }

  return (
    <aside
      className="disclosures-widget"
      data-testid="disclosures-widget"
      aria-label="공시 일정"
    >
      <h3 className="dsc-title">
        공시 일정 <span className="dsc-scope">· 희석/배당</span>
      </h3>
      <ul className="dsc-list" data-testid="disclosures-list">
        {items.map((item, i) => {
          const dilutive = isDilutive(item.kind);
          return (
            <li
              key={`${item.date}-${item.ticker}-${i}`}
              className={`dsc-row${dilutive ? ' dsc-row--risk' : ''}`}
              data-testid="disclosure-item"
              data-dilutive={dilutive ? 'true' : 'false'}
            >
              <div className="dsc-row-head">
                <span className="dsc-date mono">{item.date}</span>
                <span className="dsc-name">{item.name}</span>
                <span className="dsc-code mono">{item.ticker}</span>
                <span className={`dsc-kind ${kindClass(item.kind)}`}>
                  {item.kind}
                </span>
              </div>
              <p className="dsc-item-title" title={item.title}>
                {item.title}
              </p>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
