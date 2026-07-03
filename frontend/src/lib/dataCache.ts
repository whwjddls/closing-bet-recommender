// 화면 전환(라우팅 remount)마다 위젯이 재조회하면서, 실패/빈 응답이 기존 지표를
// 덮어써 "지표가 사라지는" 버그를 막는 얇은 캐시.
// 스캔 실행 중엔 KIS/KRX 자원을 스캔이 점유해 위젯 재조회가 자주 실패하는데,
// 그때도 직전 값을 유지해 보여준다.
//
// 규칙:
//  1. 신선한(TTL 이내) 캐시가 있으면 네트워크 없이 즉시 반환 → 재mount 순간 표시.
//  2. 만료/미존재면 fetcher 실행. 성공(비어있지 않음)이면 캐시 갱신 후 반환.
//  3. fetcher 실패 또는 빈 결과(null/undefined/빈 배열)면 기존 캐시를 유지해 반환한다
//     (빈 값으로 절대 덮지 않는다). 캐시가 없으면 실패는 전파, 빈 결과는 그대로 반환
//     (위젯이 정직한 placeholder를 그리도록).

interface CacheEntry {
  value: unknown;
  at: number;
}

const store = new Map<string, CacheEntry>();

// 실패에 준하는 "빈" 응답 판정. 우리 API는 대부분 envelope 객체라 바 배열이 드물지만,
// null/undefined/빈 배열을 방어적으로 빈 값으로 본다(객체는 유효한 응답으로 취급).
function isEmptyResult(value: unknown): boolean {
  if (value === null || value === undefined) return true;
  if (Array.isArray(value)) return value.length === 0;
  return false;
}

export async function cachedFetch<T>(
  key: string,
  fetcher: () => Promise<T>,
  ttlMs = 60_000,
): Promise<T> {
  const entry = store.get(key);
  // 1) 신선한 캐시 → 네트워크 없이 즉시 반환
  if (entry && Date.now() - entry.at < ttlMs) {
    return entry.value as T;
  }

  try {
    const value = await fetcher();
    if (isEmptyResult(value)) {
      // 3) 빈 결과는 기존 캐시를 덮지 않는다
      if (entry) return entry.value as T;
      return value; // 캐시 없음 → 정직한 빈 결과 그대로
    }
    // 2) 유효 응답 → 캐시 갱신
    store.set(key, { value, at: Date.now() });
    return value;
  } catch (err) {
    // 3) 실패 시 기존값 유지
    if (entry) return entry.value as T;
    throw err; // 캐시 없음 → 실패 전파(위젯 failed placeholder)
  }
}

// 특정 키 무효화 — 데이터가 확실히 바뀐 직후(예: 채점 실행 완료 → performance)
// 다음 조회가 캐시 대신 신선한 값을 받도록 한다.
export function invalidateCache(key: string): void {
  store.delete(key);
}

// 테스트 격리용 — 모듈 전역 캐시를 비운다.
export function clearDataCache(): void {
  store.clear();
}
