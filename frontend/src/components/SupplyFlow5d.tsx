import type { Supply5d } from '../api/client';

interface Props {
  supply: Supply5d | null;
}

// 억 단위 라벨(백엔드가 억 단위 순매수 값을 준다고 가정). 부호 유지.
function formatNet(v: number): string {
  const sign = v > 0 ? '+' : v < 0 ? '−' : '';
  return `${sign}${Math.abs(v).toLocaleString('ko-KR')}`;
}

function dirClass(v: number): string {
  if (v > 0) return 'up';
  if (v < 0) return 'down';
  return 'flat';
}

// 종목별 최근 5거래일 투자자 수급 막대(외인/기관).
// +매수=상승빨강 위쪽 / −매도=하락파랑 아래쪽. 0선 기준 대칭 막대.
function FlowRow({
  label,
  values,
  dates,
  testid,
}: {
  label: string;
  values: number[];
  dates: string[];
  testid: string;
}) {
  const max = Math.max(1, ...values.map((v) => Math.abs(v)));
  return (
    <div className="sf-row" data-testid={testid}>
      <span className="sf-row-label">{label}</span>
      <ol className="sf-bars" aria-label={`${label} 5일 순매수`}>
        {values.map((v, i) => {
          const dir = dirClass(v);
          const heightPct = (Math.abs(v) / max) * 50; // 0선 위/아래 최대 50%
          return (
            <li key={dates[i] ?? i} className="sf-bar-cell">
              <span className="sf-bar-track">
                <span
                  className={`sf-bar sf-bar-${dir}`}
                  data-testid="supply-bar"
                  data-dir={dir}
                  style={{ height: `${Math.max(heightPct, 1.5)}%` }}
                  title={`${dates[i] ?? ''} · ${formatNet(v)}`}
                />
              </span>
              <span className="sf-bar-date">{(dates[i] ?? '').slice(5)}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export default function SupplyFlow5d({ supply }: Props) {
  if (!supply || supply.dates.length === 0) {
    return (
      <section
        className="supply-flow supply-flow--empty"
        data-testid="supply-5d"
        aria-label="종목 5일 수급"
      >
        <h3 className="sf-title">최근 5일 수급 (외인·기관)</h3>
        <p className="sf-empty" data-testid="supply-5d-empty">
          수급 데이터 없음
        </p>
      </section>
    );
  }

  return (
    <section
      className="supply-flow"
      data-testid="supply-5d"
      aria-label="종목 5일 수급"
    >
      <h3 className="sf-title">
        최근 5일 수급 <span className="sf-scope">외인·기관 순매수</span>
      </h3>
      <FlowRow
        label="외인"
        values={supply.foreign}
        dates={supply.dates}
        testid="supply-foreign"
      />
      <FlowRow
        label="기관"
        values={supply.institution}
        dates={supply.dates}
        testid="supply-institution"
      />
      <p className="sf-legend">
        <span className="dir-up">■</span> 순매수 ·{' '}
        <span className="dir-down">■</span> 순매도
      </p>
    </section>
  );
}
