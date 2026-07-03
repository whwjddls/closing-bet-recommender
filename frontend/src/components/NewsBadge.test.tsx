import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import NewsBadge from './NewsBadge';
import * as api from '../api/client';

beforeEach(() => vi.restoreAllMocks());

// mount fetch promise 정리(act 경고 방지 + 상태 반영 flush)
async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('NewsBadge', () => {
  it('뉴스가 있으면 건수 배지 + 제목 미리보기 툴팁을 보여준다', async () => {
    vi.spyOn(api, 'fetchNews').mockResolvedValue({
      items: [
        { datetime: '20260703 1510', title: 'OpenAI 협업 발표' },
        { datetime: '20260703 1420', title: '대규모 수주 공시' },
      ],
    });
    render(<NewsBadge ticker="000660" />);
    const badge = await screen.findByTestId('news-badge');
    expect(badge).toHaveTextContent('뉴스 2건');
    expect(badge.getAttribute('title')).toContain('OpenAI 협업 발표');
    expect(badge.getAttribute('title')).toContain('직접 판단');
  });

  it('뉴스가 없으면 "뉴스 없음" — 재료 없음으로 단정하지 않는 문구', async () => {
    vi.spyOn(api, 'fetchNews').mockResolvedValue({ items: [] });
    render(<NewsBadge ticker="000660" />);
    const badge = await screen.findByTestId('news-badge-none');
    expect(badge).toHaveTextContent('뉴스 없음');
    expect(badge.getAttribute('title')).toContain('한 번 더 확인');
  });

  it('조회 실패 시 아무것도 표시하지 않는다(추측 금지)', async () => {
    vi.spyOn(api, 'fetchNews').mockRejectedValue(new Error('network'));
    render(<NewsBadge ticker="000660" />);
    await flush();
    expect(screen.queryByTestId('news-badge')).not.toBeInTheDocument();
    expect(screen.queryByTestId('news-badge-none')).not.toBeInTheDocument();
  });

  it('같은 종목 재mount 시 캐시로 재조회하지 않는다', async () => {
    const spy = vi.spyOn(api, 'fetchNews').mockResolvedValue({
      items: [{ datetime: '20260703 1510', title: '수주' }],
    });
    const { unmount } = render(<NewsBadge ticker="000660" />);
    await screen.findByTestId('news-badge');
    unmount();
    render(<NewsBadge ticker="000660" />);
    await screen.findByTestId('news-badge');
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
