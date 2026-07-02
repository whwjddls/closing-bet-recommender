import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import RegimeGauge from './RegimeGauge';
import type { RegimeInfo } from '../api/client';

const mk = (market: 'KOSPI' | 'KOSDAQ', mult: number): RegimeInfo => ({
  market,
  index_level: 2700,
  ma5: 2680,
  cond_a: mult > 0,
  cond_b: mult >= 1,
  regime_mult: mult,
});

describe('RegimeGauge', () => {
  it('두 시장의 regime_mult를 상태색과 함께 보여준다', () => {
    render(<RegimeGauge regimes={[mk('KOSPI', 1.0), mk('KOSDAQ', 0.5)]} />);
    const kospi = screen.getByTestId('regime-KOSPI');
    expect(kospi).toHaveTextContent('1.0');
    expect(kospi).toHaveAttribute('data-level', 'on');
    const kosdaq = screen.getByTestId('regime-KOSDAQ');
    expect(kosdaq).toHaveAttribute('data-level', 'half');
  });

  it('regime 0.0은 off 레벨 + 쉬어가기 라벨', () => {
    render(<RegimeGauge regimes={[mk('KOSPI', 0.0)]} />);
    const pill = screen.getByTestId('regime-KOSPI');
    expect(within(pill).getByText('0.0x')).toBeInTheDocument();
    expect(pill).toHaveTextContent('쉬어가기');
    expect(pill).toHaveAttribute('data-level', 'off');
  });
});
