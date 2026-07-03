import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import { clearDataCache } from '../lib/dataCache';

afterEach(() => {
  cleanup();
  clearDataCache(); // 모듈 전역 위젯 캐시가 테스트 간 누수되지 않도록
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
