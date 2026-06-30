import type { Recommendation } from '../api/client';

export interface Badge {
  key: string;
  label: string;
}

// Recommendation 신호 필드 → 표시용 배지 칩(key는 CSS/식별, label은 표기).
export function deriveBadges(rec: Recommendation): Badge[] {
  const badges: Badge[] = [];
  if (rec.near_252 >= 0.99) badges.push({ key: 'shin', label: '신고가' });
  if (rec.rvol >= 2) badges.push({ key: 'rvol', label: 'RVOL' });
  if (rec.supply_tilt > 1.0) badges.push({ key: 'supply_up', label: '수급+' });
  if (rec.supply_tilt < 1.0) badges.push({ key: 'supply_down', label: '수급-' });
  if (rec.regime_mult === 1.0) badges.push({ key: 'regime_on', label: '시황●' });
  if (rec.regime_mult === 0.5)
    badges.push({ key: 'regime_half', label: '시황◐' });
  if (rec.base_flag) badges.push({ key: 'base', label: '베이스' });
  if (rec.provisional_flag) badges.push({ key: 'provisional', label: '잠정' });
  return badges;
}
