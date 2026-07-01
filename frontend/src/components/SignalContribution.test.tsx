import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import SignalContribution from './SignalContribution';
import type { StockContributions } from '../api/client';

const contributions: StockContributions = {
  s_shin: 1.16,
  rvol_confirm: 0.93,
  supply_tilt: 1.03,
  regime_mult: 1.0,
  veto: 1,
  core: 1.12,
};

describe('SignalContribution', () => {
  it('각 신호 기여도(s_shin·rvol_confirm·supply_tilt·regime_mult·veto·core·final)를 보여준다', () => {
    render(<SignalContribution contributions={contributions} final={1.12} />);
    expect(screen.getByTestId('contrib-s_shin')).toHaveTextContent('1.16');
    expect(screen.getByTestId('contrib-rvol_confirm')).toHaveTextContent('0.93');
    expect(screen.getByTestId('contrib-supply_tilt')).toHaveTextContent('1.03');
    expect(screen.getByTestId('contrib-regime_mult')).toHaveTextContent('1.00');
    expect(screen.getByTestId('contrib-veto')).toHaveTextContent('1');
    expect(screen.getByTestId('contrib-core')).toHaveTextContent('1.12');
    expect(screen.getByTestId('contrib-final')).toHaveTextContent('1.12');
  });
});
