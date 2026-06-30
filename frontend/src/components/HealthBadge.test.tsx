import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import HealthBadge from './HealthBadge';
import type { HealthResponse } from '../api/client';

const ok: HealthResponse = {
  status: 'OK',
  kis_coverage_pct: 92,
  board_published: true,
  last_run_date: '2026-06-30',
  reason: '',
};

describe('HealthBadge', () => {
  it('OK 상태와 커버리지%를 보여준다', () => {
    render(<HealthBadge health={ok} />);
    const badge = screen.getByTestId('health-badge');
    expect(badge).toHaveTextContent('OK');
    expect(badge).toHaveTextContent('92%');
    expect(badge).toHaveAttribute('data-status', 'OK');
  });

  it('DOWN 상태는 사유를 노출한다', () => {
    render(
      <HealthBadge
        health={{
          ...ok,
          status: 'DOWN',
          kis_coverage_pct: 0,
          reason: 'KIS 미수신',
        }}
      />,
    );
    const badge = screen.getByTestId('health-badge');
    expect(badge).toHaveAttribute('data-status', 'DOWN');
    expect(badge).toHaveTextContent('KIS 미수신');
  });
});
