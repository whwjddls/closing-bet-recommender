import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import CalendarWidget from './CalendarWidget';
import * as api from '../api/client';
import type { CalendarResponse } from '../api/client';

const calendar: CalendarResponse = {
  today: {
    date: '2026-07-02',
    is_trading_day: true,
    session_type: '정규',
    close_time: '15:30',
  },
  upcoming: [
    { date: '2026-07-10', kind: 'expiry', label: '선물옵션 동시만기(네마녀)', d_day: 8 },
    { date: '2026-07-03', kind: 'ex_dividend', label: '중간배당 배당락', d_day: 1 },
    { date: '2026-08-15', kind: 'holiday', label: '광복절 휴장', d_day: 44 },
  ],
};

beforeEach(() => vi.restoreAllMocks());

describe('CalendarWidget', () => {
  it('오늘 세션과 다가오는 일정을 D-day 오름차순으로 렌더한다', async () => {
    vi.spyOn(api, 'fetchCalendar').mockResolvedValue(calendar);
    render(<CalendarWidget />);

    await waitFor(() =>
      expect(screen.getAllByTestId('calendar-event')).toHaveLength(3),
    );

    const today = screen.getByTestId('calendar-today');
    expect(today).toHaveTextContent('2026-07-02');
    expect(today).toHaveTextContent('정규장');
    expect(today).toHaveAttribute('data-trading', 'true');

    const events = screen.getAllByTestId('calendar-event');
    // 오름차순: 배당락(D-1) → 만기(D-8) → 휴장(D-44)
    expect(events[0]).toHaveTextContent('D-1');
    expect(events[0]).toHaveAttribute('data-kind', 'ex_dividend');
    expect(events[1]).toHaveTextContent('D-8');
    expect(events[2]).toHaveTextContent('D-44');
  });

  it('휴장일이면 세션 배지를 휴장으로 표시한다', async () => {
    vi.spyOn(api, 'fetchCalendar').mockResolvedValue({
      today: {
        date: '2026-08-15',
        is_trading_day: false,
        session_type: '휴장',
        close_time: '00:00',
      },
      upcoming: [],
    });
    render(<CalendarWidget />);

    const today = await screen.findByTestId('calendar-today');
    expect(today).toHaveTextContent('휴장');
    expect(today).toHaveAttribute('data-trading', 'false');
    expect(
      screen.getByTestId('calendar-upcoming-empty'),
    ).toHaveTextContent('예정된 일정 없음');
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchCalendar').mockRejectedValue(new Error('network'));
    render(<CalendarWidget />);
    expect(
      await screen.findByTestId('calendar-widget-empty'),
    ).toHaveTextContent('캘린더 데이터 없음');
  });
});
