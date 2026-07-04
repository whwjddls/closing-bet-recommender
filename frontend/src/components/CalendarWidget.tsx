import { useEffect, useState } from 'react';
import Skeleton from './Skeleton';
import {
  fetchCalendar,
  type CalendarResponse,
  type CalendarEvent,
} from '../api/client';
import { cachedFetch } from '../lib/dataCache';

// kind 문자열 → 칩 색 카테고리. 백엔드 enum 미확정이므로 토큰 매칭 + 기본값.
type KindTone = 'expiry' | 'exdiv' | 'holiday' | 'default';

function kindTone(kind: string): KindTone {
  const k = kind.toLowerCase();
  if (k.includes('expir') || kind.includes('만기') || kind.includes('네마녀'))
    return 'expiry';
  if (k.includes('div') || kind.includes('배당'))
    return 'exdiv';
  if (k.includes('holiday') || kind.includes('휴장'))
    return 'holiday';
  return 'default';
}

function ddayLabel(dDay: number): string {
  if (dDay === 0) return 'D-DAY';
  if (dDay > 0) return `D-${dDay}`;
  return `D+${Math.abs(dDay)}`;
}

function sessionTone(today: CalendarResponse['today']): {
  cls: string;
  label: string;
} {
  if (!today.is_trading_day)
    return { cls: 'session-closed', label: '휴장' };
  if (today.session_type.includes('조기'))
    return { cls: 'session-early', label: '조기폐장' };
  return { cls: 'session-open', label: '정규장' };
}

export default function CalendarWidget() {
  const [calendar, setCalendar] = useState<CalendarResponse | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    cachedFetch('calendar', fetchCalendar)
      .then((c) => {
        if (alive) setCalendar(c);
      })
      .catch(() => {
        if (alive) setFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  if (failed) {
    return (
      <aside
        className="calendar-widget calendar-widget--empty"
        data-testid="calendar-widget"
        aria-label="거래 캘린더"
      >
        <h3 className="cal-title">거래 캘린더</h3>
        <p className="cal-empty" data-testid="calendar-widget-empty">
          캘린더 데이터 없음
        </p>
      </aside>
    );
  }

  if (!calendar) {
    return (
      <aside
        className="calendar-widget"
        data-testid="calendar-widget"
        aria-label="거래 캘린더"
        aria-busy="true"
      >
        <h3 className="cal-title">거래 캘린더</h3>
        <Skeleton lines={2} />
      </aside>
    );
  }

  const { today, upcoming } = calendar;
  const session = sessionTone(today);
  const events: CalendarEvent[] = [...upcoming].sort(
    (a, b) => a.d_day - b.d_day,
  );

  return (
    <aside
      className="calendar-widget"
      data-testid="calendar-widget"
      aria-label="거래 캘린더"
    >
      <h3 className="cal-title">거래 캘린더</h3>

      <div
        className={`cal-today ${session.cls}`}
        data-testid="calendar-today"
        data-trading={today.is_trading_day ? 'true' : 'false'}
      >
        <span className="cal-today-date mono">{today.date}</span>
        <span className="cal-today-badge">{session.label}</span>
        <span className="cal-today-close mono">
          {today.is_trading_day ? `~${today.close_time}` : '거래 없음'}
        </span>
      </div>

      {events.length === 0 ? (
        <p className="cal-none" data-testid="calendar-upcoming-empty">
          예정된 일정 없음
        </p>
      ) : (
        <ul className="cal-chips" data-testid="calendar-upcoming">
          {events.map((ev, i) => (
            <li
              key={`${ev.date}-${ev.kind}-${i}`}
              className={`cal-chip cal-chip--${kindTone(ev.kind)}`}
              data-testid="calendar-event"
              data-kind={ev.kind}
            >
              <span className="cal-chip-dday mono">{ddayLabel(ev.d_day)}</span>
              <span className="cal-chip-label">{ev.label}</span>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
