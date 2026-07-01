import { describe, it, expect, vi } from 'vitest';
import { notifyTop3 } from './notify';
import type { Recommendation } from '../api/client';

const r = (rank: number, name: string): Recommendation => ({
  rank,
  ticker: String(rank),
  name,
  market: 'KOSPI',
  price_provisional: 1,
  buy_price_provisional: 1,
  buy_price_final: null,
  exit_label: '매도 오전 VWAP(09–10)',
  target_price: 1,
  stop_price: 1,
  score: 1,
  grade: 'S',
  badges: [],
  near_252: 1,
  near_60: 1,
  rvol: 1,
  s_shin: 1,
  rvol_confirm: 1,
  supply_tilt: 1,
  regime_mult: 1,
  veto: 1,
  spark: [1, 2],
  base_flag: false,
  provisional_flag: true,
});

describe('notifyTop3', () => {
  it('권한 granted면 top3 이름으로 Notification 생성', () => {
    const ctor = vi.fn();
    vi.stubGlobal('Notification', Object.assign(ctor, { permission: 'granted' }));
    notifyTop3([r(1, 'A'), r(2, 'B'), r(3, 'C'), r(4, 'D')]);
    expect(ctor).toHaveBeenCalledTimes(1);
    expect(ctor.mock.calls[0][1].body).toContain('A');
    expect(ctor.mock.calls[0][1].body).toContain('C');
    expect(ctor.mock.calls[0][1].body).not.toContain('D');
  });
  it('권한 없으면 생성하지 않음', () => {
    const ctor = vi.fn();
    vi.stubGlobal('Notification', Object.assign(ctor, { permission: 'denied' }));
    notifyTop3([r(1, 'A')]);
    expect(ctor).not.toHaveBeenCalled();
  });
});
