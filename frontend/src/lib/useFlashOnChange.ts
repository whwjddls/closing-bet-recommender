import { useEffect, useRef, useState } from 'react';

// 값이 바뀔 때만 durationMs 동안 true. 최초 마운트/동일 값은 false(불필요한 강조 방지).
// 콘솔 "숫자 변경 틱"(모션②)용 — 매초 바뀌는 시계엔 쓰지 않고 드물게 갱신되는 값에만.
export function useFlashOnChange(value: unknown, durationMs = 400): boolean {
  const [flashing, setFlashing] = useState(false);
  const prev = useRef(value);
  useEffect(() => {
    if (prev.current === value) return;
    prev.current = value;
    setFlashing(true);
    const id = window.setTimeout(() => setFlashing(false), durationMs);
    return () => window.clearTimeout(id);
  }, [value, durationMs]);
  return flashing;
}
