import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import MonthlyPerfCalendar from './MonthlyPerfCalendar';
import { kstToday } from '../lib/date';

const DAY = 86_400_000;
const d = (back: number) => kstToday(Date.now() - back * DAY);

describe('MonthlyPerfCalendar', () => {
  it('13주(91칸) 격자를 그리고 승/패 셀을 반영한다', () => {
    // 최근 3일: +0.01(win) / -0.005(loss) / +0.015(win)
    const curve = [
      { date: d(2), cum: 0.01 },
      { date: d(1), cum: 0.005 },
      { date: d(0), cum: 0.02 },
    ];
    render(<MonthlyPerfCalendar curve={curve} sampleSize={5} />);
    expect(screen.getAllByTestId('mcal-cell')).toHaveLength(91);
    const wins = screen
      .getAllByTestId('mcal-cell')
      .filter((c) => c.getAttribute('data-kind') === 'win');
    expect(wins).toHaveLength(2);
  });

  it('범례(성공/실패/관망)를 표시한다', () => {
    render(<MonthlyPerfCalendar curve={[]} sampleSize={5} />);
    const legend = screen.getByTestId('mcal-legend');
    expect(legend).toHaveTextContent('성공');
    expect(legend).toHaveTextContent('실패');
    expect(legend).toHaveTextContent('관망');
  });

  it('표본 0이면 컨테이너 안에 빈 상태', () => {
    render(<MonthlyPerfCalendar curve={[]} sampleSize={0} />);
    const c = screen.getByTestId('monthly-perf-calendar');
    expect(within(c).getByTestId('mcal-empty')).toHaveTextContent(
      '아직 기록이 없어요',
    );
  });
});
