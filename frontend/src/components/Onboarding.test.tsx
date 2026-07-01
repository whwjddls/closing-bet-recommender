import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Onboarding from './Onboarding';

const KEY = 'cbr.onboarding.dismissed.v1';

describe('Onboarding', () => {
  beforeEach(() => localStorage.clear());

  it('첫 방문에 3단계 코치마크를 노출한다', () => {
    render(<Onboarding />);
    const card = screen.getByTestId('onboarding');
    expect(card).toBeInTheDocument();
    expect(card).toHaveTextContent('색으로 등급 확인');
    expect(card).toHaveTextContent('잠정 배지 주의');
    expect(card).toHaveTextContent('담기 1~9');
    expect(card).toHaveTextContent('주문 없음');
  });

  it('닫기 → 사라지고 localStorage에 영구 플래그가 저장된다', async () => {
    render(<Onboarding />);
    await userEvent.click(screen.getByTestId('onboarding-dismiss'));
    expect(screen.queryByTestId('onboarding')).not.toBeInTheDocument();
    expect(localStorage.getItem(KEY)).toBe('1');
  });

  it('플래그가 있으면 재방문 시 숨긴다', () => {
    localStorage.setItem(KEY, '1');
    render(<Onboarding />);
    expect(screen.queryByTestId('onboarding')).not.toBeInTheDocument();
  });
});
