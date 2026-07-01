import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import IndexStrip from './IndexStrip';
import type { RegimeInfo } from '../api/client';

const mk = (
  market: 'KOSPI' | 'KOSDAQ',
  index_level: number,
  ma5: number,
  mult: number,
): RegimeInfo => ({
  market,
  index_level,
  ma5,
  regime_mult: mult,
  cond_a: mult > 0,
  cond_b: mult >= 1,
});

describe('IndexStrip', () => {
  it('시장별 지수·5일선 대비·레짐 배지를 렌더한다', () => {
    render(
      <IndexStrip
        regimes={[mk('KOSPI', 2700, 2680, 1.0), mk('KOSDAQ', 850, 860, 0.5)]}
      />,
    );

    const kospi = screen.getByTestId('index-strip-KOSPI');
    expect(kospi).toHaveTextContent('2,700');
    // index_level >= ma5 → 5MA 위(상승 빨강)
    const kospiMa = screen.getByTestId('index-ma-KOSPI');
    expect(kospiMa).toHaveTextContent('5MA 위');
    expect(kospiMa).toHaveClass('dir-up');
    expect(screen.getByTestId('index-regime-KOSPI')).toHaveAttribute(
      'data-level',
      'on',
    );

    const kosdaq = screen.getByTestId('index-strip-KOSDAQ');
    expect(kosdaq).toHaveTextContent('850');
    // index_level < ma5 → 5MA 아래(하락 파랑)
    const kosdaqMa = screen.getByTestId('index-ma-KOSDAQ');
    expect(kosdaqMa).toHaveTextContent('5MA 아래');
    expect(kosdaqMa).toHaveClass('dir-down');
    expect(screen.getByTestId('index-regime-KOSDAQ')).toHaveAttribute(
      'data-level',
      'half',
    );
  });

  it('regime_mult 0.0은 off(RISK-OFF) 배지', () => {
    render(<IndexStrip regimes={[mk('KOSPI', 2500, 2600, 0.0)]} />);
    const badge = screen.getByTestId('index-regime-KOSPI');
    expect(badge).toHaveTextContent('RISK-OFF');
    expect(badge).toHaveAttribute('data-level', 'off');
  });

  it('regimes가 비면 정직한 placeholder', () => {
    render(<IndexStrip regimes={[]} />);
    expect(screen.getByTestId('index-strip-empty')).toHaveTextContent(
      '시황 데이터 없음',
    );
  });
});
