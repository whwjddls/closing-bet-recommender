import type { UniverseRow } from '../api/client';
import { formatPrice } from '../lib/format';

export default function Scanner({ rows }: { rows: UniverseRow[] }) {
  if (rows.length === 0) {
    return <p data-testid="scan-empty">후보 풀 데이터가 없습니다.</p>;
  }
  return (
    <table className="scanner">
      <thead>
        <tr>
          <th>종목/코드</th>
          <th>시장</th>
          <th>20일평균거래대금</th>
          <th>적격</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr
            key={r.ticker}
            data-testid="scan-row"
            data-eligible={r.eligible}
            className={r.eligible ? '' : 'scan-excluded'}
          >
            <td>
              {r.name} <small>{r.ticker}</small>
            </td>
            <td>{r.market}</td>
            <td>{formatPrice(r.avg_value_20d)}</td>
            <td>
              {r.eligible ? '○' : '×'}
              {r.is_managed && <span className="tag">관리</span>}
              {r.is_warning && <span className="tag">경고</span>}
              {r.is_caution && <span className="tag">주의</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
