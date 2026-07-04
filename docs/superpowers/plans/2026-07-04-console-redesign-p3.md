# 종가베팅 콘솔 리디자인 P3 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 §1.3/§5 P3 — 콘솔 모션 언어 완성(스켈레톤 로딩 + 숫자 변경 틱) + 모바일 과밀 정리 + 빈 상태 일관화. 기능·데이터·정직성 원칙 불변.

**Architecture:** P1에서 카운트다운 펄스(모션①)는 완료됐다. P3는 ② 숫자 변경 틱 트랜지션(값이 바뀔 때만 짧게 강조 — `useFlashOnChange` 훅)과 ③ 스켈레톤 로딩(현재 "로딩 중…" 텍스트 10곳 → shimmer 블록)을 추가하고, 모바일에서 추천 테이블을 가로 스크롤 래핑하며 상단바 줄바꿈을 정리한다. 모든 신규 모션은 `prefers-reduced-motion`을 존중한다.

**Tech Stack:** React18 + Vite + TS + vitest. 신규 의존성 없음.

---

## 0. 실행 전 필독 (게이트·지뢰)

- 게이트(매 태스크): `cd frontend && npx vitest run`(현재 40파일/213) 전부 green · `npx tsc --noEmit`(**`tsc -b` 금지**) · `npx vite build` · `find src -name '*.js'` = 0
- vitest는 반드시 **`frontend/` 디렉터리에서** 실행.
- 이모지 0 유지(P1 기준 grep=✓ 외 0건). 새 코드에 이모지 금지.
- 시각 검수 스크립트는 `frontend/_shot_*.mjs`(실행 후 삭제, 커밋 금지). dev 서버 5173 가정.
- **기존 testid·카피·aria 불변**: 로딩 분기의 `aria-busy="true"`·컨테이너 testid 유지(스켈레톤은 내부 텍스트만 교체). 위젯별 로딩 클래스(`*-loading`)는 스켈레톤으로 교체하되 컨테이너 구조 유지.
- 모션은 전부 `@media (prefers-reduced-motion: no-preference)` 안에서만 정의(리셋 시 정적). 기존 파일에 이미 이 미디어쿼리 2곳 사용 중 — 동일 패턴.

## 파일 지도

| 파일 | 역할 |
|---|---|
| Create `frontend/src/components/Skeleton.tsx` (+test) | 콘솔 스켈레톤(shimmer 블록, 폭/개수 props) |
| Create `frontend/src/lib/useFlashOnChange.ts` (+test) | 값 변경 감지 → 짧게 flash 클래스 토글 훅 |
| Modify `frontend/src/styles/theme.css` | shimmer·tick-flash keyframe + 모바일 반응형(테이블 스크롤·상단바) |
| Modify 로딩 표시 위젯 10곳 | "로딩 중…" → `<Skeleton>` |
| Modify `frontend/src/components/FunnelPanel.tsx` (+test) | 추천 수·커버리지 값 변경 시 tick flash |
| Modify `frontend/src/pages/Board.tsx` | 추천 테이블 가로 스크롤 래퍼 |

---

### Task 1: Skeleton 컴포넌트 (TDD)

**Files:** Create `frontend/src/components/Skeleton.tsx`, `frontend/src/components/Skeleton.test.tsx`; Modify `theme.css`

콘솔 스켈레톤: 헤어라인 배경 위 shimmer가 지나가는 블록 `lines`개. `prefers-reduced-motion` 시 shimmer 없이 정적 블록.

- [ ] **Step 1-1: 실패 테스트** — `Skeleton.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import Skeleton from './Skeleton';

describe('Skeleton', () => {
  it('기본 1줄 스켈레톤 + 로딩 접근성(aria-busy, 스크린리더 텍스트)', () => {
    render(<Skeleton />);
    const sk = screen.getByTestId('skeleton');
    expect(sk).toHaveAttribute('aria-busy', 'true');
    expect(sk).toHaveTextContent('로딩 중'); // sr-only 유지(스크린리더)
    expect(screen.getAllByTestId('skeleton-line')).toHaveLength(1);
  });

  it('lines 지정 개수만큼 블록을 그린다', () => {
    render(<Skeleton lines={3} />);
    expect(screen.getAllByTestId('skeleton-line')).toHaveLength(3);
  });
});
```

- [ ] **Step 1-2: 실패 확인** — `npx vitest run src/components/Skeleton.test.tsx` → 컴포넌트 없음 FAIL
- [ ] **Step 1-3: 구현** — `Skeleton.tsx`:

```tsx
// 콘솔 스켈레톤 로딩(모션③) — "로딩 중…" 텍스트 대체. shimmer는 reduced-motion 존중(CSS).
// 스크린리더용 "로딩 중" 텍스트는 sr-only로 유지(정직성·접근성).
export default function Skeleton({
  lines = 1,
  width,
}: {
  lines?: number;
  width?: string;
}) {
  return (
    <div className="skeleton" data-testid="skeleton" aria-busy="true">
      {Array.from({ length: lines }, (_, i) => (
        <span
          key={i}
          className="skeleton-line"
          data-testid="skeleton-line"
          style={width && i === lines - 1 ? { width } : undefined}
        />
      ))}
      <span className="sr-only">로딩 중…</span>
    </div>
  );
}
```

- [ ] **Step 1-4: CSS 추가** — `theme.css`(로딩 관련 근처):

```css
.skeleton {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.skeleton-line {
  height: 11px;
  border-radius: 2px;
  background: var(--bg-2);
}
/* .sr-only 는 theme.css:172~ 에 이미 존재 — 중복 선언 금지(재사용). */
@media (prefers-reduced-motion: no-preference) {
  .skeleton-line {
    background: linear-gradient(
      90deg,
      var(--bg-2) 25%,
      var(--bg-1) 37%,
      var(--bg-2) 63%
    );
    background-size: 400% 100%;
    animation: skeleton-shimmer 1.4s ease infinite;
  }
}
@keyframes skeleton-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: 0 0; }
}
```

- [ ] **Step 1-5: 통과 확인** → PASS
- [ ] **Step 1-6: Commit** — `feat(frontend): 콘솔 스켈레톤 로딩 컴포넌트(shimmer·reduced-motion)`

---

### Task 2: 로딩 표시 스켈레톤 적용 (10곳)

**Files:** Modify `CalendarWidget.tsx`, `DisclosuresWidget.tsx`, `FunnelPanel.tsx`, `MarketInvestors.tsx`, `NearHighsWidget.tsx`, `NewsPanel.tsx`, `PerfHeatmap.tsx`, `PerfSummaryCard.tsx`, `ReminderWidget.tsx`, `SectorHeatmap.tsx`

각 파일의 로딩 분기 `<p className="X-loading">로딩 중…</p>`(FunnelPanel은 `<p className="fp-skeleton">집계 중…</p>`)를 `<Skeleton lines={N} />`로 교체. **컨테이너·제목·aria-busy는 유지**(위젯 로딩 분기의 상위 `aria-busy` 속성 그대로). 위젯별 적정 lines(위젯 높이감): 리스트형(공시/신고가/리마인더/뉴스)=3, 통계형(수급/섹터/캘린더/성과카드/잔디/깔때기)=2.

- [ ] **Step 2-1: 조사** — `grep -rn "로딩 중…\|집계 중…" src --include='*.tsx'`로 10곳 재확인.
- [ ] **Step 2-2: 각 파일 교체** — import `import Skeleton from './Skeleton';`(PerfHeatmap/PerfSummaryCard 등 components 내부는 `'./Skeleton'`, 페이지/그 외는 경로 조정) 후 로딩 `<p>`를 `<Skeleton lines={2 또는 3} />`로. 예(SectorHeatmap):

```tsx
// 변경 전: <p className="sh-loading">로딩 중…</p>
<Skeleton lines={2} />
```

- [ ] **Step 2-3: 게이트** — `npx vitest run`(로딩 분기 테스트가 "로딩 중" 텍스트를 직접 단언하지 않는지 확인 — 단언하면 그 테스트를 `skeleton` 존재로 이관). tsc·build.
- [ ] **Step 2-4: 시각 확인** — 새로고침 직후(스캔 실행 중 위젯 로딩) shimmer가 뜨는지 샷 1장.
- [ ] **Step 2-5: Commit** — `feat(frontend): 로딩 표시 10곳 스켈레톤화(로딩 중… → shimmer)`

---

### Task 3: 모바일 과밀 정리

**Files:** Modify `frontend/src/pages/Board.tsx`, `frontend/src/styles/theme.css`

실측(390px): ① 추천 테이블(10컬럼)이 압축돼 셀 줄바꿈 남발 → **가로 스크롤 래핑**으로 컬럼 폭 유지. ② 상단바가 3줄로 난잡 → 줄바꿈·간격 정리.

- [ ] **Step 3-1: 테이블 스크롤 래퍼** — `Board.tsx`에서 `<RecTable .../>`을 스크롤 컨테이너로 감싼다(RecTable 내부 변경 없음 — testid 불변):

```tsx
<div className="rec-table-scroll">
  <RecTable ... />
</div>
```

CSS:
```css
.rec-table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.rec-table-scroll .rec-table {
  min-width: 720px; /* 컬럼 압축 방지 — 좁으면 가로 스크롤 */
}
```

- [ ] **Step 3-2: 상단바 반응형** — `theme.css`의 `.global-header`/`.gh-right`에 모바일 규칙:

```css
@media (max-width: 640px) {
  .global-header {
    flex-wrap: wrap;
    height: auto;
    row-gap: 6px;
    padding-top: 6px;
    padding-bottom: 6px;
  }
  .gh-right {
    flex-wrap: wrap;
    justify-content: flex-start;
    gap: 6px;
  }
  .gh-honesty {
    order: 10; /* 정직성 배너는 줄 맨 끝으로 밀어 한 줄 차지 */
    flex-basis: 100%;
  }
}
```
(실제 셀렉터명은 `GlobalHeader.tsx` 확인 후 일치시킬 것 — `global-header`·`gh-right`·`gh-honesty` testid/class 존재 확인됨.)

- [ ] **Step 3-3: 게이트 + 모바일 샷** — 390px 보드 재촬영, 테이블 가로 스크롤·상단바 정돈 확인.
- [ ] **Step 3-4: Commit** — `fix(frontend): 모바일 과밀 정리 — 추천 테이블 가로 스크롤·상단바 줄바꿈`

---

### Task 4: 숫자 변경 틱 트랜지션 (모션②)

**Files:** Create `frontend/src/lib/useFlashOnChange.ts`, `frontend/src/lib/useFlashOnChange.test.ts`; Modify `frontend/src/components/FunnelPanel.tsx` (+test); `theme.css`

값이 **바뀔 때만** 짧게(약 0.4s) 강조. 매초 바뀌는 시계/경과초에는 적용하지 않고, 스캔 완료로 드물게 갱신되는 값(걸러내기 추천 수·커버리지)에만 적용해 트레이딩 콘솔의 "틱" 감을 준다. reduced-motion 시 무효.

- [ ] **Step 4-1: 실패 테스트(훅)** — `useFlashOnChange.test.ts`:

```ts
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useFlashOnChange } from './useFlashOnChange';

afterEach(() => vi.useRealTimers());

describe('useFlashOnChange', () => {
  it('값이 바뀌면 flashing=true, 지정 시간 뒤 false', () => {
    vi.useFakeTimers();
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v, 400), {
      initialProps: { v: 1 },
    });
    expect(result.current).toBe(false); // 최초엔 flash 없음
    rerender({ v: 2 });
    expect(result.current).toBe(true); // 변경 → flash
    act(() => vi.advanceTimersByTime(400));
    expect(result.current).toBe(false); // 시간 뒤 해제
  });

  it('같은 값 재렌더는 flash하지 않는다', () => {
    const { result, rerender } = renderHook(({ v }) => useFlashOnChange(v, 400), {
      initialProps: { v: 5 },
    });
    rerender({ v: 5 });
    expect(result.current).toBe(false);
  });
});
```

- [ ] **Step 4-2: 실패 확인** → 훅 없음 FAIL
- [ ] **Step 4-3: 구현(훅)** — `useFlashOnChange.ts`:

```ts
import { useEffect, useRef, useState } from 'react';

// 값이 바뀔 때만 durationMs 동안 true. 최초 마운트/동일 값은 false(불필요한 강조 방지).
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
```

- [ ] **Step 4-4: FunnelPanel 적용** — 실패 테스트 먼저(`FunnelPanel.test.tsx`): board가 추천 3→다른 값으로 리렌더되면 `funnel-flow`에 `tick-flash` 클래스가 잠깐 붙는지(간단히: 최초엔 없음 단언):

```tsx
it('최초 렌더에는 tick-flash가 없다(값 미변경)', () => {
  render(<FunnelPanel universeCount={200} board={{ ...boardBase, recommendations: [] }} />);
  expect(screen.getByTestId('funnel-flow').className).not.toContain('tick-flash');
});
```
  구현: `const flash = useFlashOnChange(picks);` 후 `funnel-flow`에 `className={`fp-flow${flash ? ' tick-flash' : ''}`}`. (picks 문자열 값 기준.)
- [ ] **Step 4-5: CSS** — `theme.css`:

```css
@media (prefers-reduced-motion: no-preference) {
  .tick-flash {
    animation: tick-flash 0.4s ease;
  }
}
@keyframes tick-flash {
  0% { background: var(--accent); filter: brightness(1.15); }
  100% { background: transparent; }
}
```
(배경 플래시가 과하면 `color`/`outline` 플래시로 완화 — Task 5 샷에서 판단.)
- [ ] **Step 4-6: 통과 + 게이트** → PASS
- [ ] **Step 4-7: Commit** — `feat(frontend): 숫자 변경 틱 트랜지션(useFlashOnChange) — 걸러내기 값 강조`

---

### Task 5: 빈 상태 일관화 + reduced-motion 감사 + 최종 검수

**Files:** Modify `theme.css`(필요시), 최종 검수

- [ ] **Step 5-1: 빈 상태 감사** — 빈 상태 문구/스타일 통일 확인(grep `데이터 없음\|기록이 없어요\|추천이 없\|일정 없음`). 콘솔 톤 이탈(색/여백)만 미세 조정 — 문구 변경 금지(정직성 카피 불변).
- [ ] **Step 5-2: reduced-motion 감사** — 신규 모션(skeleton-shimmer·tick-flash) 전부 `@media (prefers-reduced-motion: no-preference)` 안에 있는지 확인. 기존 card-rise는 이미 가드됨. 가드 밖 모션 2개 — `blink`(`.gh-countdown.gh-danger` ~660행)·`gh-countdown-pulse`(`.gh-countdown--hot` ~598행) — 를 가드 안으로 넣는다. **주의: `animation:` 선언만** `@media (prefers-reduced-motion: no-preference)` 블록으로 옮기고, 해당 셀렉터의 color/background/border(danger/hot 상태색)는 무조건 유지(reduced-motion 사용자도 상태색은 봐야 함).
- [ ] **Step 5-3: 전체 게이트** — `npx vitest run` · `npx tsc --noEmit` · `npx vite build` · `.js`=0
- [ ] **Step 5-4: 이모지 0 검증** — `LC_ALL=C.UTF-8 grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{2300}-\x{23FF}]" src --include='*.ts' --include='*.tsx' --include='*.css'` → `✓` 외 0건
- [ ] **Step 5-5: 샷** — 데스크톱(보드·성과) + 모바일(390px 보드) + reduced-motion(에뮬레이트) 확인.
- [ ] **Step 5-6: WORK-PLAN §5 P3 완료 한 줄 + 계획서 체크박스 갱신 후 Commit** — `docs: 콘솔 리디자인 P3 완료 기록`

---

## 참고 — 순서 의존성·예상

| Task | 의존 | 예상 |
|---|---|---|
| 1 Skeleton | — | 25분 |
| 2 로딩 적용 | 1 | 30분 |
| 3 모바일 | — | 30분 |
| 4 틱 트랜지션 | — | 30분 |
| 5 감사·검수 | 전부 | 25분 |

P3 완료 시 콘솔 리디자인(P1~P3) 전체 종료.
