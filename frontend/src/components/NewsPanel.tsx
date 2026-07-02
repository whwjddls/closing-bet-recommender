import { useEffect, useState } from 'react';
import { fetchNews, type NewsItem } from '../api/client';

// GET /news/{ticker} — "최근 뉴스(재료 확인)" 리스트. 빈/실패는 정직한 placeholder.
export default function NewsPanel({ ticker }: { ticker: string }) {
  const [items, setItems] = useState<NewsItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    setItems(null);
    setFailed(false);
    fetchNews(ticker)
      .then((res) => {
        if (alive) setItems(res.items);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, [ticker]);

  const hasItems = (items?.length ?? 0) > 0;

  const title = (
    <h3 className="news-title">
      최근 뉴스 <span className="news-scope">· 재료 확인</span>
    </h3>
  );

  // 실패 또는 빈 응답 → 크래시 없이 안내.
  if (failed || (items && !hasItems)) {
    return (
      <section
        className="news-panel news-panel--empty card"
        data-testid="news-panel"
        aria-label="최근 뉴스"
      >
        {title}
        <p className="news-empty" data-testid="news-empty">
          표시할 뉴스가 없어요 (장중에 조회돼요)
        </p>
      </section>
    );
  }

  if (!items) {
    return (
      <section
        className="news-panel card"
        data-testid="news-panel"
        aria-label="최근 뉴스"
        aria-busy="true"
      >
        {title}
        <p className="news-loading">로딩 중…</p>
      </section>
    );
  }

  return (
    <section
      className="news-panel card"
      data-testid="news-panel"
      aria-label="최근 뉴스"
    >
      {title}
      <ul className="news-list" data-testid="news-list">
        {items.map((item, i) => (
          <li key={`${item.datetime}-${i}`} className="news-item" data-testid="news-item">
            <time className="news-time mono">{item.datetime}</time>
            <span className="news-headline">{item.title}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
