import { useEffect, useState } from 'react';
import {
  fetchReminder,
  type ReminderResponse,
  type ReminderPick,
} from '../api/client';
import { cachedFetch } from '../lib/dataCache';

// 전략의 나머지 절반 — 매수만큼 청산도 규칙. 어제 픽들의 익일 오전 매도 관리 뷰.
// morning_vwap 이 null 이면 KIS 분봉 미연동으로 청산 기준을 아직 추정 못함(정직 표기).

type OutcomeTone = 'success' | 'fail' | 'na';

function outcomeMeta(outcome: string | null): {
  tone: OutcomeTone;
  label: string;
} {
  const o = (outcome ?? '').toUpperCase();
  if (o === 'SUCCESS') return { tone: 'success', label: '성공' };
  if (o === 'FAIL') return { tone: 'fail', label: '실패' };
  return { tone: 'na', label: 'N·A' };
}

function won(value: number): string {
  return value.toLocaleString('ko-KR');
}

function priceOrDash(value: number | null): string {
  return value == null ? '—' : won(value);
}

export default function ReminderWidget() {
  const [data, setData] = useState<ReminderResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch('reminder', fetchReminder)
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

  const picks: ReminderPick[] = data?.picks ?? [];
  const hasPicks = picks.length > 0;

  const header = (
    <div className="rmd-head">
      <h3 className="rmd-title">다음날 아침 팔기 알림</h3>
      <p className="rmd-caption" data-testid="reminder-caption">
        다음날 아침 9~10시에 파는 게 전략의 나머지 절반이에요
      </p>
    </div>
  );

  // fetch 실패 또는 빈 목록 → 정직한 placeholder (크래시 없음).
  if (failed || (data && !hasPicks)) {
    return (
      <aside
        className="reminder-widget reminder-widget--empty"
        data-testid="reminder-widget"
        aria-label="익일 오전 청산 리마인더"
      >
        {header}
        <p className="rmd-empty" data-testid="reminder-widget-empty">
          어제 추천이 없습니다
        </p>
      </aside>
    );
  }

  if (!data) {
    return (
      <aside
        className="reminder-widget"
        data-testid="reminder-widget"
        aria-label="익일 오전 청산 리마인더"
        aria-busy="true"
      >
        {header}
        <p className="rmd-loading">로딩 중…</p>
      </aside>
    );
  }

  return (
    <aside
      className="reminder-widget"
      data-testid="reminder-widget"
      aria-label="익일 오전 청산 리마인더"
    >
      {header}
      <ul className="rmd-list" data-testid="reminder-list">
        {picks.map((pick, i) => {
          const pending = pick.morning_vwap == null;
          const outcome = outcomeMeta(pick.outcome);
          return (
            <li
              key={`${pick.ticker}-${i}`}
              className={`rmd-row grade-${pick.grade}`}
              data-testid="reminder-item"
              data-pending={pending ? 'true' : 'false'}
            >
              <div className="rmd-row-head">
                <span className={`grade-badge grade-${pick.grade}`}>
                  {pick.grade}
                </span>
                <span className="rmd-name">{pick.name}</span>
                <span className="rmd-code mono">{pick.ticker}</span>
              </div>

              <div className="rmd-prices">
                <span className="rmd-cell">
                  <span className="rmd-cell-label">매수 참고가</span>
                  <span className="rmd-cell-val mono">
                    {priceOrDash(pick.buy_price)}
                  </span>
                </span>
                <span className="rmd-cell">
                  <span className="rmd-cell-label">참고 목표</span>
                  <span className="rmd-cell-val mono dir-up">
                    {won(pick.target_price)}
                  </span>
                </span>
                <span className="rmd-cell">
                  <span className="rmd-cell-label">참고 손절</span>
                  <span className="rmd-cell-val mono dir-down">
                    {won(pick.stop_price)}
                  </span>
                </span>
              </div>

              <div className="rmd-exit">
                <span className="rmd-exit-label">팔 때 기준 · 아침 평균가</span>
                {pending ? (
                  <span
                    className="rmd-vwap-pending"
                    data-testid="reminder-vwap-pending"
                    title="KIS 분봉 미연동으로 오전 VWAP 추정 불가"
                  >
                    추정 미연동(KIS)
                  </span>
                ) : (
                  <span className="rmd-exit-known">
                    <span className="rmd-vwap-val mono">
                      {won(pick.morning_vwap as number)}
                    </span>
                    <span
                      className={`rmd-outcome rmd-outcome--${outcome.tone}`}
                      data-testid="reminder-outcome"
                      data-outcome={outcome.tone}
                    >
                      {outcome.label}
                    </span>
                  </span>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
