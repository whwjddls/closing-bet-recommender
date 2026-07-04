import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Skeleton from './Skeleton';

describe('Skeleton', () => {
  it('기본 1줄 스켈레톤 + 로딩 접근성(aria-busy, 스크린리더 텍스트)', () => {
    render(<Skeleton />);
    const sk = screen.getByTestId('skeleton');
    expect(sk).toHaveAttribute('aria-busy', 'true');
    expect(sk).toHaveTextContent('로딩 중'); // sr-only 유지(스크린리더)
    expect(screen.getAllByTestId('skeleton-line')).toHaveLength(1);
  });

  it('lines 지정 개수만큼 블록을 그린다', () => {
    render(<Skeleton lines={3} />);
    expect(screen.getAllByTestId('skeleton-line')).toHaveLength(3);
  });
});
