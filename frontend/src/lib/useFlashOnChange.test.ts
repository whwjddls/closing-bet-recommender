import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFlashOnChange } from './useFlashOnChange';

afterEach(() => vi.useRealTimers());

describe('useFlashOnChange', () => {
  it('값이 바뀌면 flashing=true, 지정 시간 뒤 false', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(
      ({ v }) => useFlashOnChange(v, 400),
      { initialProps: { v: 1 } },
    );
    expect(result.current).toBe(false); // 최초엔 flash 없음
    rerender({ v: 2 });
    expect(result.current).toBe(true); // 변경 → flash
    act(() => vi.advanceTimersByTime(400));
    expect(result.current).toBe(false); // 시간 뒤 해제
  });

  it('같은 값 재렌더는 flash하지 않는다', () => {
    const { result, rerender } = renderHook(
      ({ v }) => useFlashOnChange(v, 400),
      { initialProps: { v: 5 } },
    );
    rerender({ v: 5 });
    expect(result.current).toBe(false);
  });
});
