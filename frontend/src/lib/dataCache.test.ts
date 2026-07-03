import { describe, it, expect, vi, beforeEach } from 'vitest';
import { cachedFetch, clearDataCache, invalidateCache } from './dataCache';

beforeEach(() => clearDataCache());

describe('cachedFetch', () => {
  it('신선한 캐시가 있으면 fetcher를 다시 호출하지 않고 즉시 반환한다', async () => {
    const payload = { items: [1, 2] };
    const fetcher = vi.fn().mockResolvedValue(payload);

    const first = await cachedFetch('k', fetcher, 60_000);
    const second = await cachedFetch('k', fetcher, 60_000);

    expect(first).toBe(payload);
    expect(second).toBe(payload);
    expect(fetcher).toHaveBeenCalledTimes(1); // 두 번째는 캐시
  });

  it('fetcher 실패 시 기존 캐시 값을 유지해 반환한다', async () => {
    const good = { items: ['a'] };
    // ttl 0 → 매 호출 stale 처리(항상 재조회 경로)
    await cachedFetch('k', vi.fn().mockResolvedValue(good), 0);

    const failing = vi.fn().mockRejectedValue(new Error('스캔이 자원 점유'));
    const result = await cachedFetch('k', failing, 0);

    expect(failing).toHaveBeenCalled(); // 재조회는 시도했고
    expect(result).toEqual(good); // 실패했지만 기존값 유지
  });

  it('빈 결과(빈 배열)는 기존 캐시를 덮지 않는다', async () => {
    const good = [1, 2, 3];
    await cachedFetch('k', vi.fn().mockResolvedValue(good), 0);

    const empty = await cachedFetch('k', vi.fn().mockResolvedValue([]), 0);

    expect(empty).toEqual(good); // 빈 배열이 기존값을 덮지 않음
  });

  it('캐시가 없을 때 실패는 그대로 전파한다', async () => {
    await expect(
      cachedFetch('nokey', vi.fn().mockRejectedValue(new Error('down')), 0),
    ).rejects.toThrow('down');
  });

  it('캐시가 없을 때 빈 결과는 그대로 반환한다(정직한 placeholder)', async () => {
    const result = await cachedFetch('nokey', vi.fn().mockResolvedValue([]), 0);
    expect(result).toEqual([]);
  });

  it('clearDataCache 후에는 fetcher를 다시 호출한다', async () => {
    const fetcher = vi.fn().mockResolvedValue({ v: 1 });
    await cachedFetch('k', fetcher, 60_000);
    clearDataCache();
    await cachedFetch('k', fetcher, 60_000);
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it('invalidateCache는 해당 키만 무효화한다', async () => {
    const fa = vi.fn().mockResolvedValue({ v: 'a' });
    const fb = vi.fn().mockResolvedValue({ v: 'b' });
    await cachedFetch('a', fa, 60_000);
    await cachedFetch('b', fb, 60_000);

    invalidateCache('a');

    await cachedFetch('a', fa, 60_000); // 무효화된 키 → 재조회
    await cachedFetch('b', fb, 60_000); // 다른 키 → 캐시 유지
    expect(fa).toHaveBeenCalledTimes(2);
    expect(fb).toHaveBeenCalledTimes(1);
  });
});
