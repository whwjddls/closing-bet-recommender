import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { createChart } from 'lightweight-charts';
import { fetchStock, type StockContributions, type StockDetailResponse } from '../api/client';
import { formatPrice } from '../lib/format';
import SignalContribution from '../components/SignalContribution';
import OvernightGapStat from '../components/OvernightGapStat';
import VolumeHistogram from '../components/VolumeHistogram';
import SupplyFlow5d from '../components/SupplyFlow5d';
import DisclosuresWidget from '../components/DisclosuresWidget';
import NewsPanel from '../components/NewsPanel';

interface PriceLineSpec {
  price: number;
  color: string;
  title: string;
}

// 같은/근접(±0.5%) 가격의 라벨이 차트에서 겹쳐 쌓이는 문제 해결.
// 근접한 라인들을 하나로 병합해 라벨을 "1년 최고가·전고점"처럼 합친다.
// 가격이 큰 순으로 정렬 후 그룹 대표가 대비 0.5% 이내면 같은 그룹으로 묶는다.
const PRICE_MERGE_TOLERANCE = 0.005;

// 차트는 canvas(lightweight-charts)라 CSS 변수가 자동 적용되지 않는다.
// 현재 테마 토큰을 읽어 라인색을 맞춘다(읽기 실패 시 양테마 무난한 폴백).
function themeColor(varName: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback;
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
  return value || fallback;
}

function mergePriceLines(specs: PriceLineSpec[]): PriceLineSpec[] {
  const sorted = [...specs].sort((a, b) => b.price - a.price);
  const groups: PriceLineSpec[][] = [];
  for (const spec of sorted) {
    const group = groups[groups.length - 1];
    const ref = group?.[0].price;
    if (group && ref && Math.abs(spec.price - ref) / ref <= PRICE_MERGE_TOLERANCE) {
      group.push(spec);
    } else {
      groups.push([spec]);
    }
  }
  return groups.map((group) => ({
    price: group[0].price,
    color: group[0].color,
    title: group.map((s) => s.title).join('·'),
  }));
}

export default function StockDetail() {
  const { code } = useParams<{ code: string }>();
  const [detail, setDetail] = useState<StockDetailResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chartRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!code) return;
    fetchStock(code)
      .then(setDetail)
      .catch((e) => setError(String(e)));
  }, [code]);

  useEffect(() => {
    if (!detail || !chartRef.current) return;
    const chart = createChart(chartRef.current, { height: 320 });
    const series = chart.addCandlestickSeries();
    series.setData(
      detail.candles.map((c) => ({
        time: c.date,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
      })),
    );
    const upColor = themeColor('--up', '#e5484d'); // 1년 최고가(강세 빨강)
    const downColor = themeColor('--down', '#2563eb'); // 전고점(파랑)
    const flatColor = themeColor('--flat', '#94a3b8'); // 눌림 구간(중립 회색)
    const priceLines: PriceLineSpec[] = [
      { price: detail.high_52w, color: upColor, title: '1년 최고가' },
      { price: detail.prior_high, color: downColor, title: '전고점' },
    ];
    if (detail.base_box) {
      priceLines.push({ price: detail.base_box.high, color: flatColor, title: '눌림 상단' });
      priceLines.push({ price: detail.base_box.low, color: flatColor, title: '눌림 하단' });
    }
    for (const line of mergePriceLines(priceLines)) {
      series.createPriceLine(line);
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [detail]);

  if (error) return <p data-testid="detail-error">불러오기 실패: {error}</p>;
  if (!detail) return <p className="board-loading">로딩 중…</p>;

  return (
    <main className="stock-detail">
      {/* ── 상단 요약 바 ─────────────────────────────────────── */}
      <header className="sd-summary card">
        <div className="sd-summary-id">
          {detail.grade ? (
            <span className={`grade-badge grade-${detail.grade}`}>
              {detail.grade}
            </span>
          ) : (
            <span className="grade-badge grade-ref" data-testid="reference-badge"
                  title="추천 목록에 없는 종목 — 차트·통계만 참고하세요">
              참고
            </span>
          )}
          <h1 className="sd-name">
            {detail.name}
            <span className="sd-code mono">{detail.ticker}</span>
          </h1>
        </div>
        <div className="sd-summary-metrics">
          <div className="sd-metric">
            <span className="sd-metric-label">현재가</span>
            <span className="sd-metric-val mono">
              {formatPrice(detail.price_provisional)}
              <sup
                data-testid="provisional-watermark"
                className="sd-prov"
                title="15:20 기준 값 — 마감(15:30) 때 바뀔 수 있어요"
              >
                15:20 기준
              </sup>
            </span>
          </div>
          <div className="sd-metric">
            <span className="sd-metric-label">종합 점수</span>
            <span className="sd-metric-val mono">
              {detail.final != null ? detail.final.toFixed(2) : '—'}
            </span>
          </div>
        </div>
      </header>

      {/* ── 2컬럼: 왜 추천? / 뭘 조심? ─────────────────────────── */}
      <div className="sd-cols">
        <section className="sd-col sd-why" aria-label="왜 추천?">
          <h2 className="sd-col-title sd-col-title--why">
            왜 추천? <small>이 종목을 고른 이유</small>
          </h2>

          <div ref={chartRef} data-testid="daily-chart" className="sd-chart" />

          <VolumeHistogram candles={detail.candles} />

          {detail.final != null && (
            <SignalContribution
              contributions={detail.contributions as StockContributions}
              final={detail.final}
            />
          )}

          <SupplyFlow5d supply={detail.supply_5d} />
        </section>

        <section className="sd-col sd-watch" aria-label="뭘 조심?">
          <h2 className="sd-col-title sd-col-title--watch">
            뭘 조심? <small>사기 전에 확인</small>
          </h2>

          <OvernightGapStat gap={detail.overnight_gap} />

          <div className="sd-stop card" data-testid="sd-stop">
            <h3 className="sd-stop-title">참고 손절(계속 들고 갈 때)</h3>
            <p className="sd-stop-body">
              단타 기본은 <strong>다음날 아침 9~10시 매도</strong>예요. 그래도
              계속 들고 간다면, 아래 <strong>하룻밤 가격 변동</strong> 통계의
              최악 5% 하락폭을 손절 기준으로 참고하세요.
            </p>
          </div>

          {detail.base_box && (
            <p data-testid="base-box" className="sd-basebox card">
              눌림 구간 {formatPrice(detail.base_box.low)}~
              {formatPrice(detail.base_box.high)} ({detail.base_box.start}~
              {detail.base_box.end})
            </p>
          )}

          <DisclosuresWidget />
        </section>
      </div>

      {/* ── 최근 뉴스(재료 확인) ─────────────────────────────── */}
      {code && <NewsPanel ticker={code} />}
    </main>
  );
}
