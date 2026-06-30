import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from './App';

describe('App 라우팅 셸', () => {
  it('네비게이션에 보드/성과 링크를 렌더한다', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: '추천보드' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '성과추적' })).toBeInTheDocument();
  });
});
