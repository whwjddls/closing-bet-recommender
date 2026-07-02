import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ReminderWidget from './ReminderWidget';
import * as api from '../api/client';
import type { ReminderResponse } from '../api/client';

const reminder: ReminderResponse = {
  picks: [
    {
      ticker: '000660',
      name: 'SK하이닉스',
      grade: 'S',
      buy_price: 24500,
      target_price: 25000,
      stop_price: 23800,
      outcome: 'SUCCESS',
      morning_vwap: 24980,
    },
    {
      ticker: '005930',
      name: '삼성전자',
      grade: 'B',
      buy_price: 71000,
      target_price: 73000,
      stop_price: 69500,
      outcome: null,
      morning_vwap: null, // KIS 분봉 미연동 → 추정 불가
    },
  ],
};

beforeEach(() => vi.restoreAllMocks());

describe('ReminderWidget', () => {
  it('어제 픽을 매수가·목표가·손절가와 함께 렌더한다', async () => {
    vi.spyOn(api, 'fetchReminder').mockResolvedValue(reminder);
    render(<ReminderWidget />);

    await waitFor(() =>
      expect(screen.getAllByTestId('reminder-item')).toHaveLength(2),
    );

    const rows = screen.getAllByTestId('reminder-item');
    expect(rows[0]).toHaveTextContent('SK하이닉스');
    expect(rows[0]).toHaveTextContent('000660');
    expect(rows[0]).toHaveTextContent('25,000'); // 목표가
    expect(rows[0]).toHaveTextContent('23,800'); // 손절가
    expect(rows[0]).toHaveTextContent('24,500'); // 매수가
  });

  it('헤더에 "전략의 나머지 절반" 캡션을 노출한다', async () => {
    vi.spyOn(api, 'fetchReminder').mockResolvedValue(reminder);
    render(<ReminderWidget />);

    expect(await screen.findByTestId('reminder-caption')).toHaveTextContent(
      '전략의 나머지 절반',
    );
  });

  it('morning_vwap 이 있으면 값 + outcome 배지, 없으면 "추정 미연동(KIS)" 배지', async () => {
    vi.spyOn(api, 'fetchReminder').mockResolvedValue(reminder);
    render(<ReminderWidget />);

    await waitFor(() =>
      expect(screen.getAllByTestId('reminder-item')).toHaveLength(2),
    );

    // 1번째 픽: VWAP 값 + 성공 배지
    const rows = screen.getAllByTestId('reminder-item');
    expect(rows[0]).toHaveAttribute('data-pending', 'false');
    expect(rows[0]).toHaveTextContent('24,980');
    const outcome = screen.getByTestId('reminder-outcome');
    expect(outcome).toHaveTextContent('성공');
    expect(outcome).toHaveAttribute('data-outcome', 'success');

    // 2번째 픽: 미연동 회색 배지(정직 표기), outcome 배지 없음
    expect(rows[1]).toHaveAttribute('data-pending', 'true');
    const pending = screen.getByTestId('reminder-vwap-pending');
    expect(pending).toHaveTextContent('추정 미연동(KIS)');
  });

  it('빈 목록이면 "어제 추천이 없습니다" placeholder', async () => {
    vi.spyOn(api, 'fetchReminder').mockResolvedValue({ picks: [] });
    render(<ReminderWidget />);

    expect(
      await screen.findByTestId('reminder-widget-empty'),
    ).toHaveTextContent('어제 추천이 없습니다');
  });

  it('fetch 실패해도 크래시 없이 placeholder', async () => {
    vi.spyOn(api, 'fetchReminder').mockRejectedValue(new Error('network'));
    render(<ReminderWidget />);

    expect(
      await screen.findByTestId('reminder-widget-empty'),
    ).toHaveTextContent('어제 추천이 없습니다');
  });
});
