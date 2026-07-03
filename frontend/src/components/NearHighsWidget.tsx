import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchHighs, type HighItem } from '../api/client';
import { cachedFetch } from '../lib/dataCache';

// GET /highs — 52주 신고가 근접 종목(장중 KIS 조회). 빈 배열/실패는 정직한 placeholder.
// 신고가 근접은 강세 신호 → 한국 관례색 상승빨강 톤으로 칩을 표기한다.
export default function NearHighsWidget() {
  const [items, setItems] = useState<HighItem[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch('highs', fetchHighs)
      .then((res) => {
        if (alive) setItems(res.items);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const hasItems = (items?.length ?? 0) > 0;

  // 실패 또는 빈 응답(장중 미조회 포함) → 크래시 없이 안내.
  if (failed || (items && !hasItems)) {
    return (
      <aside
        className="near-highs near-highs--empty"
        data-testid="near-highs"
        aria-label="1년 최고가 근접"
      >
        <h3 className="nh-title">1년 최고가 근접</h3>
        <p className="nh-empty" data-testid="near-highs-empty">
          데이터 없음(장중 조회)
        </p>
      </aside>
    );
  }

  if (!items) {
    return (
      <aside
        className="near-highs"
        data-testid="near-highs"
        aria-label="1년 최고가 근접"
        aria-busy="true"
      >
        <h3 className="nh-title">1년 최고가 근접</h3>
        <p className="nh-loading">로딩 중…</p>
      </aside>
    );
  }

  return (
    <aside
      className="near-highs"
      data-testid="near-highs"
      aria-label="1년 최고가 근접"
    >
      <h3 className="nh-title">
        1년 최고가 근접 <span className="nh-scope">· 최근 1년</span>
      </h3>
      <ul className="nh-chips" data-testid="near-highs-chips">
        {items.map((it) => (
          <li key={it.ticker}>
            <Link
              className="nh-chip"
              data-testid="near-high-chip"
              to={`/stock/${it.ticker}`}
            >
              <span className="nh-chip-name">{it.name || it.ticker}</span>
              <span className="nh-chip-code">{it.ticker}</span>
            </Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
