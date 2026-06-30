import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MiniChart from './MiniChart';

describe('MiniChart', () => {
  it('데이터 포인트 수만큼 polyline 좌표를 생성한다', () => {
    render(<MiniChart data={[10, 12, 11, 15]} />);
    const line = screen.getByTestId('mini-chart').querySelector('polyline')!;
    const points = line.getAttribute('points')!.trim().split(/\s+/);
    expect(points).toHaveLength(4);
  });

  it('상승 추세는 up, 하락은 down 트렌드 색', () => {
    const { rerender } = render(<MiniChart data={[10, 20]} />);
    expect(screen.getByTestId('mini-chart')).toHaveAttribute(
      'data-trend',
      'up',
    );
    rerender(<MiniChart data={[20, 10]} />);
    expect(screen.getByTestId('mini-chart')).toHaveAttribute(
      'data-trend',
      'down',
    );
  });

  it('데이터 1개 이하는 빈 차트 placeholder', () => {
    render(<MiniChart data={[]} />);
    expect(screen.getByTestId('mini-chart')).toHaveAttribute(
      'data-empty',
      'true',
    );
  });

  it('undefined 데이터는 빈 차트 placeholder', () => {
    render(<MiniChart data={undefined} />);
    expect(screen.getByTestId('mini-chart')).toHaveAttribute(
      'data-empty',
      'true',
    );
  });
});
