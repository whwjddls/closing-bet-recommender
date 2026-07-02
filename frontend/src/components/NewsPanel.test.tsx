import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import NewsPanel from './NewsPanel';
import * as api from '../api/client';

beforeEach(() => vi.restoreAllMocks());

describe('NewsPanel', () => {
  it('뉴스 항목을 시각·제목과 함께 렌더한다', async () => {
    vi.spyOn(api, 'fetchNews').mockResolvedValue({
      items: [
        { datetime: '2026-07-02 14:05', title: '3분기 대규모 수주 공시' },
        { datetime: '2026-07-02 09:31', title: '증권사 목표가 상향' },
      ],
    });
    render(<NewsPanel ticker="000660" />);

    await waitFor(() =>
      expect(screen.getAllByTestId('news-item')).toHaveLength(2),
    );
    const items = screen.getAllByTestId('news-item');
    expect(items[0]).toHaveTextContent('3분기 대규모 수주 공시');
    expect(items[0]).toHaveTextContent('2026-07-02 14:05');
    expect(api.fetchNews).toHaveBeenCalledWith('000660');
  });

  it('빈 응답이면 정직한 placeholder', async () => {
    vi.spyOn(api, 'fetchNews').mockResolvedValue({ items: [] });
    render(<NewsPanel ticker="000660" />);
    expect(await screen.findByTestId('news-empty')).toHaveTextContent(
      '표시할 뉴스가 없어요',
    );
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchNews').mockRejectedValue(new Error('network'));
    render(<NewsPanel ticker="000660" />);
    expect(await screen.findByTestId('news-empty')).toHaveTextContent(
      '표시할 뉴스가 없어요',
    );
  });
});
