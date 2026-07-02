import type { PickResult } from '../api/client';
import { formatPrice, formatPercent, directionClass } from '../lib/format';

const OUTCOME_LABEL: Record<PickResult['outcome'], string> = {
  SUCCESS: '✅성공',
  FAIL: '❌실패',
  NA: 'N/A',
};

// FAIL 사유별 색: 갭하락(하방 손실)=적색, 장중반전=앰버, 그 외=중립.
function failReasonClass(reason: string): string {
  if (reason.includes('갭하락')) return 'fail-reason--gap';
  if (reason.includes('장중반전') || reason.includes('반전'))
    return 'fail-reason--reversal';
  return 'fail-reason--other';
}

export default function PerfTable({ rows }: { rows: PickResult[] }) {
  if (rows.length === 0) {
    return <p data-testid="perf-empty">채점할 어제 픽이 없습니다.</p>;
  }
  return (
    <table className="perf-table">
      <thead>
        <tr>
          <th>종목</th>
          <th>등급</th>
          <th>매수가(확정)</th>
          <th>오전VWAP</th>
          <th>오전수익률</th>
          <th>결과</th>
          <th>DART재스캔</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={r.ticker}
            data-testid="perf-row"
            data-outcome={r.outcome}
            className={`perf-${r.outcome.toLowerCase()}`}
          >
            <td>
              {r.name} <small>{r.ticker}</small>
            </td>
            <td>{r.grade}</td>
            <td>{r.buy_price_final === null ? '(미확정)' : formatPrice(r.buy_price_final)}</td>
            <td data-testid="perf-vwap">
              {r.vwap_0900_1000 === null ? '(잠김)' : formatPrice(r.vwap_0900_1000)}
            </td>
            <td
              data-testid="perf-return"
              className={`num dir-${directionClass(r.morning_return)}`}
            >
              {formatPercent(r.morning_return)}
            </td>
            <td>
              {OUTCOME_LABEL[r.outcome]}
              {r.outcome === 'FAIL' && r.fail_reason && (
                <span
                  data-testid="fail-reason"
                  className={`fail-reason ${failReasonClass(r.fail_reason)}`}
                >
                  {r.fail_reason}
                </span>
              )}
            </td>
            <td>
              {r.dart_overnight_flag && (
                <span data-testid="dart-flag" className="tag-dart">
                  ⚠공시
                </span>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
