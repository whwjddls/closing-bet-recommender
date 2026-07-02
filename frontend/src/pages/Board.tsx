import { useCallback, useEffect, useState } from 'react';
import {
  fetchRecommendations,
  fetchUniverse,
  fetchHealth,
  type RecommendationsResponse,
  type UniverseResponse,
  type HealthResponse,
} from '../api/client';
import { notifyTop3 } from '../lib/notify';
import { REFETCH_EVENT } from '../lib/events';
import RecTable from '../components/RecTable';
import RegimeGauge from '../components/RegimeGauge';
import Scanner from '../components/Scanner';
import HealthBadge from '../components/HealthBadge';
import IndexStrip from '../components/IndexStrip';
import SectorHeatmap from '../components/SectorHeatmap';
import MarketInvestors from '../components/MarketInvestors';
import NearHighsWidget from '../components/NearHighsWidget';
import CalendarWidget from '../components/CalendarWidget';
import DisclosuresWidget from '../components/DisclosuresWidget';
import PicksTray, { PicksTraySpacer } from '../components/PicksTray';
import ReminderWidget from '../components/ReminderWidget';
import Onboarding from '../components/Onboarding';

function todayKst(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function Board() {
  const [board, setBoard] = useState<RecommendationsResponse | null>(null);
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // 담은 픽 티커 집합(클라이언트 전용 상태 — 신규 API 없음).
  const [pickedTickers, setPickedTickers] = useState<Set<string>>(
    () => new Set(),
  );

  const togglePick = (ticker: string) =>
    setPickedTickers((prev) => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
  const clearPicks = () => setPickedTickers(new Set());

  const loadBoard = useCallback(() => {
    setError(null);
    Promise.all([
      fetchRecommendations(todayKst()),
      fetchUniverse(),
      fetchHealth(),
    ])
      .then(([b, u, h]) => {
        setBoard(b);
        setUniverse(u);
        setHealth(h);
        notifyTop3(b.recommendations);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (
      typeof Notification !== 'undefined' &&
      Notification.permission === 'default'
    ) {
      Notification.requestPermission?.();
    }
    loadBoard();
  }, [loadBoard]);

  // 스캔 실행 완료(RunScanButton) → 보드 데이터 재조회.
  useEffect(() => {
    const handler = () => loadBoard();
    window.addEventListener(REFETCH_EVENT, handler);
    return () => window.removeEventListener(REFETCH_EVENT, handler);
  }, [loadBoard]);

  if (error)
    return (
      <>
        <IndexStrip regimes={[]} />
        <main>
          <p data-testid="board-error">보드를 불러오지 못했습니다: {error}</p>
        </main>
      </>
    );
  if (!board)
    return (
      <>
        <IndexStrip regimes={[]} />
        <main>
          <p>로딩 중…</p>
        </main>
      </>
    );

  const regimes = Object.values(board.regimes);
  const isRiskOff =
    regimes.length > 0 && regimes.every((r) => r.regime_mult === 0);
  const hasReducedRisk = regimes.some((r) => r.regime_mult === 0.5);
  const pickedRecs = board.recommendations.filter((r) =>
    pickedTickers.has(r.ticker),
  );

  return (
    <>
      <IndexStrip regimes={regimes} />
      <main>
      <Onboarding />
      <header>
        <h1>종가베팅 추천 {board.run_date}</h1>
        <RegimeGauge regimes={regimes} />
        {health && <HealthBadge health={health} />}
        <span>
          {' '}
          세션 {board.session_type ?? '-'} · 커버리지 {board.kis_coverage_pct}%
        </span>
        {universe && (
          <span
            className="scan-pool-badge"
            data-testid="scan-pool-badge"
            title="장전 스캔 유니버스(후보 풀) 규모"
          >
            스캔 풀 {universe.rows.length}종목
          </span>
        )}
      </header>

      {hasReducedRisk && (
        <p
          data-testid="reduced-risk-caption"
          className="caption-reduced-risk"
        >
          반-리스크 레짐(0.5x): 일부 시장이 약화/눌림 상태입니다.
        </p>
      )}

      <div className="board-top">
        <CalendarWidget />
        <div className="board-market-panel">
          <SectorHeatmap />
          <div className="board-side-stack">
            <MarketInvestors />
            <NearHighsWidget />
          </div>
        </div>
      </div>

      <div className="board-widgets">
        <DisclosuresWidget />
      </div>

      {board.recommendations.length === 0 ? (
        isRiskOff ? (
          <section data-testid="risk-off-banner" className="banner-risk-off">
            <strong>오늘은 시황 레짐상 추천 없음</strong>
            <p>
              RISK_OFF (모든 시장 5MA 아래). 시스템 정상 — 스캐너/최근 레짐
              컨텍스트를 유지합니다.
            </p>
            {universe && (
              <Scanner rows={universe.rows} asOf={universe.as_of} />
            )}
          </section>
        ) : (
          <p data-testid="board-empty">발행된 추천 종목이 없습니다.</p>
        )
      ) : (
        <RecTable
          recommendations={board.recommendations}
          pickedTickers={pickedTickers}
          onTogglePick={togglePick}
        />
      )}
        <section className="board-reminder" data-testid="board-reminder">
          <ReminderWidget />
        </section>
        <PicksTraySpacer />
      </main>
      <PicksTray
        picks={pickedRecs}
        onRemove={togglePick}
        onClear={clearPicks}
      />
    </>
  );
}
