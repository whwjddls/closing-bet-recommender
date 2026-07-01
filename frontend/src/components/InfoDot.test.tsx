import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InfoDot from './InfoDot';

describe('InfoDot', () => {
  it('기본 상태에서는 툴팁을 숨긴다', () => {
    render(<InfoDot label="등급" text="설명 텍스트" />);
    expect(screen.queryByTestId('info-tip')).not.toBeInTheDocument();
    // 버튼은 접근 가능한 라벨을 갖는다.
    expect(
      screen.getByRole('button', { name: '등급 설명' }),
    ).toBeInTheDocument();
  });

  it('hover 시 툴팁 텍스트가 나타난다', async () => {
    render(<InfoDot label="RVOL" text="평소 대비 오늘 거래량 배수" />);
    await userEvent.hover(screen.getByTestId('info-dot'));
    expect(screen.getByTestId('info-tip')).toHaveTextContent(
      '평소 대비 오늘 거래량 배수',
    );
  });

  it('focus 시 role=tooltip 팝오버가 뜨고 blur 시 사라진다', () => {
    render(<InfoDot label="오전VWAP" text="청산 기준" />);
    const dot = screen.getByTestId('info-dot');
    fireEvent.focus(dot);
    expect(screen.getByRole('tooltip')).toHaveTextContent('청산 기준');
    expect(dot).toHaveAttribute('aria-describedby');
    fireEvent.blur(dot);
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
  });
});
