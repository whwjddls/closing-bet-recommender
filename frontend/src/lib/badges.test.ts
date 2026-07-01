import { describe, it, expect } from 'vitest';
import { deriveBadges } from './badges';
import type { Recommendation } from '../api/client';

const base: Recommendation = {
  rank: 1,
  ticker: '000660',
  name: 'A',
  market: 'KOSDAQ',
  price_provisional: 24500,
  buy_price_provisional: 24500,
  buy_price_final: null,
  exit_label: '익일 오전 VWAP(09:00–10:00)',
  target_price: 25000,
  stop_price: 23800,
  score: 1.12,
  grade: 'S',
  near_252: 1.02,
  near_60: 1.04,
  rvol: 2.5,
  s_shin: 1.16,
  rvol_confirm: 0.93,
  supply_tilt: 1.03,
  regime_mult: 1.0,
  veto: 1,
  spark: [1, 2, 3],
  base_flag: false,
  provisional_flag: true,
};

describe('deriveBadges', () => {
  it('전고점 돌파 + RVOL + 수급+ + 시황● + 잠정 배지', () => {
    const keys = deriveBadges(base).map((b) => b.key);
    expect(keys).toContain('shin');
    expect(keys).toContain('rvol');
    expect(keys).toContain('supply_up');
    expect(keys).toContain('regime_on');
    expect(keys).toContain('provisional');
  });
  it('수급 패널티(supply_tilt<1)는 supply_down', () => {
    const keys = deriveBadges({ ...base, supply_tilt: 0.9 }).map((b) => b.key);
    expect(keys).toContain('supply_down');
  });
  it('regime 0.5는 reduced-risk 배지', () => {
    const keys = deriveBadges({ ...base, regime_mult: 0.5 }).map((b) => b.key);
    expect(keys).toContain('regime_half');
  });
  it('base_flag면 베이스 배지', () => {
    const keys = deriveBadges({ ...base, base_flag: true }).map((b) => b.key);
    expect(keys).toContain('base');
  });
  it('콜드스타트: near_252/rvol 이 null 이면 예외 없이 shin/rvol 배지를 생략', () => {
    const keys = deriveBadges({ ...base, near_252: null, rvol: null }).map(
      (b) => b.key,
    );
    expect(keys).not.toContain('shin');
    expect(keys).not.toContain('rvol');
    expect(keys).toContain('supply_up'); // 다른 배지는 정상 산출
  });
});
