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

  it('5승수 막대(신·거·시황·수급·재)를 1.0 기준 방향색으로 렌더한다', () => {
    render(<SignalContribution contributions={contributions} final={1.12} />);
    expect(screen.getByTestId('mult-bars')).toBeInTheDocument();
    // s_shin 1.16 > 1 → up(부스트), rvol 0.93 < 1 → down(드래그), regime 1.0 → flat
    expect(screen.getByTestId('mult-bar-s_shin')).toHaveAttribute('data-dir', 'up');
    expect(screen.getByTestId('mult-bar-rvol_confirm')).toHaveAttribute(
      'data-dir',
      'down',
    );
    expect(screen.getByTestId('mult-bar-regime_mult')).toHaveAttribute(
      'data-dir',
      'flat',
    );
    expect(screen.getByTestId('mult-bar-supply_tilt')).toBeInTheDocument();
    expect(screen.getByTestId('mult-bar-veto')).toBeInTheDocument();
  });
});
