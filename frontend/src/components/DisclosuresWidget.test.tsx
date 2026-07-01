import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DisclosuresWidget from './DisclosuresWidget';
import * as api from '../api/client';
import type { DisclosuresResponse } from '../api/client';

const disclosures: DisclosuresResponse = {
  items: [
    {
      date: '2026-07-01',
      ticker: '000660',
      name: 'SK하이닉스',
      kind: '유상증자',
      title: '주주배정 유상증자 결정',
    },
    {
      date: '2026-07-02',
      ticker: '005930',
      name: '삼성전자',
      kind: '배당',
      title: '중간배당 결정 공시',
    },
  ],
};

beforeEach(() => vi.restoreAllMocks());

describe('DisclosuresWidget', () => {
  it('공시 리스트를 날짜·종목·kind 배지·제목과 함께 렌더한다', async () => {
    vi.spyOn(api, 'fetchDisclosures').mockResolvedValue(disclosures);
    render(<DisclosuresWidget />);

    await waitFor(() =>
      expect(screen.getAllByTestId('disclosure-item')).toHaveLength(2),
    );

    const rows = screen.getAllByTestId('disclosure-item');
    expect(rows[0]).toHaveTextContent('SK하이닉스');
    expect(rows[0]).toHaveTextContent('000660');
    expect(rows[0]).toHaveTextContent('유상증자');
    expect(rows[0]).toHaveTextContent('주주배정 유상증자 결정');
  });

  it('희석성 공시는 리스크 톤(data-dilutive)으로 강조한다', async () => {
    vi.spyOn(api, 'fetchDisclosures').mockResolvedValue(disclosures);
    render(<DisclosuresWidget />);

    await waitFor(() =>
      expect(screen.getAllByTestId('disclosure-item')).toHaveLength(2),
    );

    const rows = screen.getAllByTestId('disclosure-item');
    // 유상증자=희석성 → risk, 배당=비희석 → neutral
    expect(rows[0]).toHaveAttribute('data-dilutive', 'true');
    expect(rows[1]).toHaveAttribute('data-dilutive', 'false');
  });

  it('빈 공시면 정직한 placeholder', async () => {
    vi.spyOn(api, 'fetchDisclosures').mockResolvedValue({ items: [] });
    render(<DisclosuresWidget />);
    expect(
      await screen.findByTestId('disclosures-widget-empty'),
    ).toHaveTextContent('공시 데이터 없음');
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchDisclosures').mockRejectedValue(new Error('network'));
    render(<DisclosuresWidget />);
    expect(
      await screen.findByTestId('disclosures-widget-empty'),
    ).toHaveTextContent('공시 데이터 없음');
  });
});
