// KST(UTC+9) 시간 유틸. UTC 자정~09:00 사이 `toISOString()` 이 어제 날짜를 주는
// 버그를 막기 위해 오프셋을 더한 뒤 날짜만 잘라낸다.
// 헤더·보드가 반드시 이 한 유틸을 공유해 같은 거래일을 조회하도록 한다.
const KST_OFFSET_MS = 9 * 3600 * 1000;

// 오늘(KST) 날짜 YYYY-MM-DD. `now` 주입으로 테스트 가능(비결정성 제거).
export function kstToday(now: number = Date.now()): string {
  return new Date(now + KST_OFFSET_MS).toISOString().slice(0, 10);
}
