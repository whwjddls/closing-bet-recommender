import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import OvernightGapStat from './OvernightGapStat';
import type { OvernightGap } from '../api/client';

const gap: OvernightGap = {
  mean: 0.003,
  std: 0.021,
  worst5pct: -0.032,
  n: 44,
};

describe('OvernightGapStat', () => {
  it('평균·변동성·최악5%·표본 통계를 렌더한다', () => {
    render(<OvernightGapStat gap={gap} />);
    expect(screen.getByTestId('overnight-gap-mean')).toHaveTextContent('+0.30%');
    expect(screen.getByTestId('overnight-gap-std')).toHaveTextContent('2.1%');
    expect(screen.getByTestId('overnight-gap-worst')).toHaveTextContent(
      '-3.20%',
    );
    expect(screen.getByTestId('overnight-gap-n')).toHaveTextContent('44');
    // 정직성 라벨: 표본 n·기간 명시
    expect(screen.getByTestId('overnight-gap')).toHaveTextContent(
      '이 종목 과거 44일',
    );
    // 한 줄 해석
    expect(screen.getByTestId('overnight-gap-summary')).toHaveTextContent(
      'n=44',
    );
  });

  it('평균 갭 부호에 따라 방향색을 부여한다', () => {
    const { rerender } = render(<OvernightGapStat gap={gap} />);
    // mean > 0 → 상승(빨강)
    expect(screen.getByTestId('overnight-gap-mean')).toHaveClass('dir-up');

    rerender(<OvernightGapStat gap={{ ...gap, mean: -0.005 }} />);
    // mean < 0 → 하락(파랑)
    expect(screen.getByTestId('overnight-gap-mean')).toHaveClass('dir-down');
    // 최악5%는 하방 꼬리 강조(risk 적색) 클래스
    expect(screen.getByTestId('overnight-gap-worst')).toHaveClass('og-worst');
  });

  it('표본 부족(null)이면 회색 placeholder', () => {
    render(<OvernightGapStat gap={null} />);
    expect(screen.getByTestId('overnight-gap-empty')).toHaveTextContent(
      '표본 부족(<20일)',
    );
    expect(screen.queryByTestId('overnight-gap-mean')).not.toBeInTheDocument();
  });
});
