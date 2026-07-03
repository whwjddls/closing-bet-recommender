import { useEffect, useState } from 'react';
import { fetchNews, type NewsItem } from '../api/client';
import { cachedFetch } from '../lib/dataCache';

// 재료(주도 테마·뉴스) 확인 배지 — 퀀트 필터가 못 보는 '오늘의 재료'를 매수 전에
// 사람이 확인하도록 돕는다(TOP3 카드용). 뉴스 유무·제목만 보여주고,
// "주도 테마인지" 판단은 사람 몫 — 자동으로 재료라고 단정하지 않는다(정직성 원칙).
const NEWS_TTL_MS = 5 * 60_000;
const PREVIEW_MAX = 3;

export default function NewsBadge({ ticker }: { ticker: string }) {
  const [items, setItems] = useState<NewsItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch(`news:${ticker}`, () => fetchNews(ticker), NEWS_TTL_MS)
      .then((d) => {
        if (alive) setItems(d.items ?? []);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [ticker]);

  // 로딩 중/조회 실패 — 아무것도 표시하지 않는다(추측성 표시 금지).
  if (failed || items === null) return null;

  if (items.length === 0) {
    return (
      <span
        className="news-badge news-badge--none"
        data-testid="news-badge-none"
        title="KIS에서 조회된 최근 뉴스가 없어요(장중 조회가 더 정확) — 포털 검색으로 한 번 더 확인 추천"
      >
        뉴스 없음
      </span>
    );
  }

  const preview = items
    .slice(0, PREVIEW_MAX)
    .map((n) => `· ${n.title}`)
    .join('\n');
  return (
    <span
      className="news-badge news-badge--has"
      data-testid="news-badge"
      title={`최근 뉴스 ${items.length}건 — 주도 테마(재료)인지 직접 판단하세요\n${preview}`}
    >
      📰 뉴스 {items.length}건
    </span>
  );
}
