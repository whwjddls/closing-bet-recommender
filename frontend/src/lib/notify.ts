import type { Recommendation } from '../api/client';

// 10분 결정창: 권한이 있을 때만 top3 이름으로 데스크톱 알림을 띄운다.
// Notification API가 없거나 권한이 없으면 조용히 무시(크래시 금지).
export function notifyTop3(recs: Recommendation[]): void {
  if (typeof Notification === 'undefined') return;
  if (Notification.permission !== 'granted') return;
  const top3 = recs.filter((r) => r.rank <= 3).map((r) => r.name);
  if (top3.length === 0) return;
  new Notification(`종가베팅 추천 ${recs.length}건 도착`, {
    body: top3.join(', '),
  });
}
