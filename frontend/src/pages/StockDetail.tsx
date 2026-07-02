import { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { createChart } from 'lightweight-charts';
import { fetchStock, type StockDetailResponse } from '../api/client';
import { formatPrice } from '../lib/format';
import SignalContribution from '../components/SignalContribution';
import OvernightGapStat from '../components/OvernightGapStat';
import VolumeHistogram from '../components/VolumeHistogram';
import SupplyFlow5d from '../components/SupplyFlow5d';

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
    series.createPriceLine({
      price: detail.high_52w,
      color: '#c00',
      title: '52주 고가',
    });
    series.createPriceLine({
      price: detail.prior_high,
      color: '#08c',
      title: '전고점',
    });
    if (detail.base_box) {
      series.createPriceLine({
        price: detail.base_box.high,
        color: '#999',
        title: '베이스 상단',
      });
      series.createPriceLine({
        price: detail.base_box.low,
        color: '#999',
        title: '베이스 하단',
      });
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [detail]);

  if (error) return <p data-testid="detail-error">불러오기 실패: {error}</p>;
  if (!detail) return <p>로딩 중…</p>;

  return (
    <main>
      <header>
        <h1>
          {detail.name} {detail.ticker} · 현재가{' '}
          {formatPrice(detail.price_provisional)}
          <sup data-testid="provisional-watermark" title="종가 확정 전 잠정값">
            {' '}
            [잠정]
          </sup>
        </h1>
        <p>
          등급 {detail.grade} · final {detail.final.toFixed(2)}
        </p>
      </header>

      <div ref={chartRef} data-testid="daily-chart" />

      <VolumeHistogram candles={detail.candles} />

      {detail.base_box && (
        <p data-testid="base-box">
          베이스 박스 {formatPrice(detail.base_box.low)}~
          {formatPrice(detail.base_box.high)} ({detail.base_box.start}~
          {detail.base_box.end})
        </p>
      )}

      <SignalContribution
        contributions={detail.contributions}
        final={detail.final}
      />

      <SupplyFlow5d supply={detail.supply_5d} />

      <OvernightGapStat gap={detail.overnight_gap} />
    </main>
  );
}
