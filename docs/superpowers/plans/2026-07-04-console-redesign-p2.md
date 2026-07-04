# 종가베팅 콘솔 리디자인 P2 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 `docs/superpowers/specs/2026-07-04-console-redesign-design.md` P2 — 성과 리포트에 **월 단위 성과 잔디(GitHub식 요일정렬 달력)** 추가 + 성과·종목 상세 페이지 콘솔 폴리시.

**Architecture:** P1에서 토큰·폰트·아이콘을 전역 교체해 두 페이지는 이미 콘솔 팔레트를 상속한다. 따라서 P2 신규 작업의 핵심은 ① 순수 날짜 유틸(요일 정렬 격자 날짜열) + ② 그것을 쓰는 `MonthlyPerfCalendar` 컴포넌트(성과 페이지 잔디 확대판)뿐이고, 나머지는 숫자 모노화·패널 일관성 폴리시다. 잔디 셀 판정은 P1의 `deriveHeatmapCells`를 재사용한다.

**Tech Stack:** React18 + Vite + TS + vitest. 신규 의존성 없음(P1의 lucide-react·폰트 재사용).

---

## 0. 실행 전 필독 (게이트·지뢰)

- 게이트(매 태스크): `cd frontend && npx vitest run`(현재 39파일/207) 전부 green · `npx tsc --noEmit`(**`tsc -b` 금지**) · `npx vite build` · `find src -name '*.js'` = 0
- vitest는 반드시 **`frontend/` 디렉터리에서** 실행(루트 실행 시 "document is not defined" 폭발 — 실사고).
- 이모지 0 유지: 새 코드에 이모지 금지. 아이콘은 lucide, 표시는 텍스트/mood-dot·잔디 셀.
- 시각 검수 스크립트는 `frontend/_shot_*.mjs`로 만들어 실행 후 **삭제**(커밋 금지). dev 서버(5173)는 떠 있다고 가정.
- 날짜는 반드시 KST 유틸(`lib/date.ts`의 `kstToday`) 기준 — `toISOString()` 직접 사용 금지(자정~09시 어제 날짜 버그 이력). 단, 요일 계산은 `new Date(dateStr + 'T00:00:00Z').getUTCDay()`로 TZ 불변 처리(아래 유틸 참조).
- **기존 testid·카피 불변**: `agg-panel`·`agg-hit-rate`·`agg-metrics`·`metric-*`·`cum-curve`·`by-grade-*`·`by-regime-*`·`cold-start-caption`·`perf-error`·PerfTable의 `perf-row`/`dart-flag` 등. 폴리시는 클래스/래핑만, testid·텍스트 콘텐츠는 유지.

## 파일 지도

| 파일 | 역할 |
|---|---|
| Modify `frontend/src/lib/perfCalendar.ts` (+test) | `weekAlignedDates(anchorToday, weeks)` 순수 유틸 추가 |
| Create `frontend/src/components/MonthlyPerfCalendar.tsx` (+test) | 성과 페이지 월 잔디(요일정렬 격자 + 월 라벨 + 범례) |
| Modify `frontend/src/pages/Performance.tsx` (+test) | 월 잔디 삽입 + 핵심 숫자 모노화 |
| Modify `frontend/src/styles/theme.css` | 월 잔디 CSS + 성과·상세 패널 폴리시 |
| Modify `frontend/src/pages/StockDetail.tsx` (+test 필요시) | 콘솔 폴리시(패널 일관성) — 구조/testid 불변 |

---

### Task 1: 요일 정렬 날짜열 유틸 (TDD)

**Files:** Modify `frontend/src/lib/perfCalendar.ts`, `frontend/src/lib/perfCalendar.test.ts`

GitHub식 잔디는 "열=주(일→토), 행=요일" 격자다. anchor(오늘)가 속한 주의 토요일에서 끝나고 `weeks`주만큼 거슬러 올라간 일요일에서 시작하는 날짜열(길이 weeks×7)을 만든다. 미래 날짜(오늘 이후~이번 주 토요일)도 포함되며, 곡선에 없으므로 skip 셀이 된다(정상 — 날이 지나며 채워짐).

- [ ] **Step 1-1: 실패 테스트** — `perfCalendar.test.ts` 끝에 추가:

```ts
import { weekAlignedDates } from './perfCalendar';

describe('weekAlignedDates', () => {
  it('anchor가 속한 주의 토요일에서 끝나고 일요일에서 시작한다', () => {
    // 2026-07-01은 수요일. 2주(14일) 격자.
    const dates = weekAlignedDates('2026-07-01', 2);
    expect(dates).toHaveLength(14);
    // 첫 날은 일요일(2026-06-21), 마지막 날은 토요일(2026-07-04)
    expect(dates[0]).toBe('2026-06-21');
    expect(dates[13]).toBe('2026-07-04');
    // 요일 정렬 검증: 인덱스 0,7 은 일요일
    const dow = (d: string) => new Date(d + 'T00:00:00Z').getUTCDay();
    expect(dow(dates[0])).toBe(0);
    expect(dow(dates[7])).toBe(0);
    expect(dow(dates[6])).toBe(6);
  });

  it('anchor가 토요일이면 그 주가 마지막 열이다', () => {
    const dates = weekAlignedDates('2026-07-04', 1); // 토요일
    expect(dates).toHaveLength(7);
    expect(dates[0]).toBe('2026-06-28'); // 일
    expect(dates[6]).toBe('2026-07-04'); // 토(=anchor)
  });
});
```

- [ ] **Step 1-2: 실패 확인** — `npx vitest run src/lib/perfCalendar.test.ts` → `weekAlignedDates` 없음 FAIL
- [ ] **Step 1-3: 구현** — `perfCalendar.ts`에 추가(파일 상단에 `const DAY_MS = 86_400_000;` 이미 없으면 추가):

```ts
const WEEK_DAY_MS = 86_400_000;

// GitHub식 잔디용 날짜열: anchorToday가 속한 주의 토요일에서 끝나고
// weeks주 거슬러 올라간 일요일에서 시작(길이 weeks×7, 일→토 순).
// 요일은 UTC 자정 기준으로 TZ 불변 계산.
export function weekAlignedDates(anchorToday: string, weeks: number): string[] {
  const anchorMs = Date.parse(anchorToday + 'T00:00:00Z');
  const dow = new Date(anchorMs).getUTCDay(); // 0=일
  const endMs = anchorMs + (6 - dow) * WEEK_DAY_MS; // 이번 주 토요일
  const total = weeks * 7;
  const startMs = endMs - (total - 1) * WEEK_DAY_MS;
  return Array.from({ length: total }, (_, i) =>
    new Date(startMs + i * WEEK_DAY_MS).toISOString().slice(0, 10),
  );
}
```

- [ ] **Step 1-4: 통과 확인** → PASS
- [ ] **Step 1-5: Commit** — `feat(frontend): 요일 정렬 잔디 날짜열 유틸(weekAlignedDates)`

---

### Task 2: MonthlyPerfCalendar 컴포넌트

**Files:** Create `frontend/src/components/MonthlyPerfCalendar.tsx`, `frontend/src/components/MonthlyPerfCalendar.test.tsx`; Modify `theme.css`

props 주도(자체 fetch 없음 — 성과 페이지가 이미 가진 aggregate 전달): `{ curve: CurvePoint[]; sampleSize: number; weeks?: number }`(기본 13주≈3개월). `deriveHeatmapCells(curve, weekAlignedDates(kstToday(), weeks))` → 열=주(일→토) 격자로 렌더. 상단 월 라벨(열의 첫 날 기준 달이 바뀌면 표기), 좌측 요일 라벨(월/수/금 sparse), 우측 범례(성공/실패/관망). sampleSize 0 → 컨테이너 안에 정직한 빈 상태.

- [ ] **Step 2-1: 실패 테스트** — `MonthlyPerfCalendar.test.tsx`:

```tsx
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import MonthlyPerfCalendar from './MonthlyPerfCalendar';
import { kstToday } from '../lib/date';

const DAY = 86_400_000;
const d = (back: number) => kstToday(Date.now() - back * DAY);

describe('MonthlyPerfCalendar', () => {
  it('13주(91칸) 격자를 그리고 승/패 셀을 반영한다', () => {
    // 최근 3일: +0.01(win) / -0.005(loss) / +0.015(win)
    const curve = [
      { date: d(2), cum: 0.01 },
      { date: d(1), cum: 0.005 },
      { date: d(0), cum: 0.02 },
    ];
    render(<MonthlyPerfCalendar curve={curve} sampleSize={5} />);
    expect(screen.getAllByTestId('mcal-cell')).toHaveLength(91);
    const wins = screen
      .getAllByTestId('mcal-cell')
      .filter((c) => c.getAttribute('data-kind') === 'win');
    expect(wins).toHaveLength(2);
  });

  it('범례(성공/실패/관망)를 표시한다', () => {
    render(<MonthlyPerfCalendar curve={[]} sampleSize={5} />);
    const legend = screen.getByTestId('mcal-legend');
    expect(legend).toHaveTextContent('성공');
    expect(legend).toHaveTextContent('실패');
    expect(legend).toHaveTextContent('관망');
  });

  it('표본 0이면 컨테이너 안에 빈 상태', () => {
    render(<MonthlyPerfCalendar curve={[]} sampleSize={0} />);
    const c = screen.getByTestId('monthly-perf-calendar');
    expect(within(c).getByTestId('mcal-empty')).toHaveTextContent(
      '아직 기록이 없어요',
    );
  });
});
```

- [ ] **Step 2-2: 실패 확인** → 컴포넌트 없음 FAIL
- [ ] **Step 2-3: 구현** — `MonthlyPerfCalendar.tsx`:

```tsx
import type { CurvePoint } from '../api/client';
import { kstToday } from '../lib/date';
import { deriveHeatmapCells, weekAlignedDates } from '../lib/perfCalendar';
import { formatPercent } from '../lib/format';

// 성과 페이지 월 잔디 — 최근 weeks주(기본 13≈3개월) 요일정렬 격자. 스펙 §2.3.
// props 주도(성과 페이지 aggregate 재사용 — 이중 fetch 없음).
const DEFAULT_WEEKS = 13;
const WD_LABELS = ['', '월', '', '수', '', '금', '']; // sparse 요일 라벨

export default function MonthlyPerfCalendar({
  curve,
  sampleSize,
  weeks = DEFAULT_WEEKS,
}: {
  curve: CurvePoint[];
  sampleSize: number;
  weeks?: number;
}) {
  const empty = sampleSize === 0;
  const dates = weekAlignedDates(kstToday(), weeks);
  const cells = empty ? [] : deriveHeatmapCells(curve, dates);
  const wins = cells.filter((c) => c.kind === 'win').length;
  const losses = cells.filter((c) => c.kind === 'loss').length;

  // 월 라벨: 각 주(열)의 첫 날(일요일) 기준 달이 바뀌면 표기.
  const monthLabels = Array.from({ length: weeks }, (_, w) => {
    const first = dates[w * 7];
    const prev = w > 0 ? dates[(w - 1) * 7] : null;
    const m = first.slice(5, 7);
    if (prev && prev.slice(5, 7) === m) return '';
    return `${Number(m)}월`;
  });

  return (
    <section
      className="monthly-perf-calendar"
      data-testid="monthly-perf-calendar"
      aria-label="성과 달력(최근 3개월)"
    >
      <div className="mcal-head">
        <span className="mcal-title">성과 달력 · 최근 3개월</span>
        <span className="mcal-legend" data-testid="mcal-legend">
          <span className="mcal-dot mcal-dot--win" /> 성공
          <span className="mcal-dot mcal-dot--loss" /> 실패
          <span className="mcal-dot mcal-dot--skip" /> 관망
        </span>
      </div>

      {empty ? (
        <p className="mcal-empty" data-testid="mcal-empty">
          아직 기록이 없어요 — 첫 채점부터 채워져요
        </p>
      ) : (
        <div className="mcal-body">
          <div className="mcal-weekdays" aria-hidden="true">
            {WD_LABELS.map((w, i) => (
              <span key={i} className="mcal-wd">
                {w}
              </span>
            ))}
          </div>
          <div className="mcal-cols">
            <div className="mcal-months" aria-hidden="true">
              {monthLabels.map((m, i) => (
                <span key={i} className="mcal-month">
                  {m}
                </span>
              ))}
            </div>
            <div
              className="mcal-grid"
              style={{ gridTemplateColumns: `repeat(${weeks}, 1fr)` }}
            >
              {cells.map((c) => (
                <span
                  key={c.date}
                  className="mcal-cell"
                  data-testid="mcal-cell"
                  data-kind={c.kind}
                  title={
                    c.delta === null
                      ? `${c.date} · 관망`
                      : `${c.date} · ${formatPercent(c.delta)}`
                  }
                />
              ))}
            </div>
          </div>
        </div>
      )}

      {!empty && (
        <p className="mcal-count mono">
          성공 {wins} · 실패 {losses}
        </p>
      )}
    </section>
  );
}
```

주의: `.mcal-grid`는 **열=주** 이므로 `grid-auto-flow: column; grid-template-rows: repeat(7,1fr)` 로 세로 채움(CSS에서). 날짜열은 일→토 순이라 열 우선 채움이면 각 열이 한 주가 된다.

- [ ] **Step 2-4: CSS 추가** — `theme.css`(PerfHeatmap 블록 근처):

```css
.monthly-perf-calendar {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 14px;
  margin: 12px 0;
}
.monthly-perf-calendar .mcal-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}
.monthly-perf-calendar .mcal-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-mid);
}
.monthly-perf-calendar .mcal-legend {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 10.5px;
  color: var(--text-lo);
}
.monthly-perf-calendar .mcal-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 1px;
  margin-left: 6px;
}
.mcal-dot--win { background: var(--cell-win); }
.mcal-dot--loss { background: var(--cell-loss); }
.mcal-dot--skip { background: var(--cell-skip); }
.monthly-perf-calendar .mcal-body {
  display: flex;
  gap: 6px;
}
.monthly-perf-calendar .mcal-weekdays {
  display: grid;
  grid-template-rows: repeat(7, 1fr);
  gap: 3px;
  padding-top: 16px; /* 월 라벨 높이만큼 정렬 */
}
.monthly-perf-calendar .mcal-wd {
  font-size: 9px;
  color: var(--text-lo);
  line-height: 1;
  display: flex;
  align-items: center;
}
.monthly-perf-calendar .mcal-cols { flex: 1; min-width: 0; }
.monthly-perf-calendar .mcal-months {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: 1fr;
  height: 14px;
  margin-bottom: 2px;
}
.monthly-perf-calendar .mcal-month {
  font-size: 9px;
  color: var(--text-lo);
}
.monthly-perf-calendar .mcal-grid {
  display: grid;
  grid-auto-flow: column;
  grid-template-rows: repeat(7, 1fr);
  gap: 3px;
}
.monthly-perf-calendar .mcal-cell {
  aspect-ratio: 1;
  border-radius: 1px;
  background: var(--cell-skip);
}
.monthly-perf-calendar .mcal-cell[data-kind='win'] { background: var(--cell-win); }
.monthly-perf-calendar .mcal-cell[data-kind='loss'] { background: var(--cell-loss); }
.monthly-perf-calendar .mcal-empty {
  margin: 0;
  color: var(--text-lo);
  font-size: 12px;
}
.monthly-perf-calendar .mcal-count {
  margin: 8px 0 0;
  font-size: 10.5px;
  color: var(--text-lo);
}
```

- [ ] **Step 2-5: 통과 + 게이트** → PASS
- [ ] **Step 2-6: Commit** — `feat(frontend): 성과 페이지 월 잔디(MonthlyPerfCalendar) — 요일정렬 3개월 격자`

---

### Task 3: Performance 페이지 통합 + 숫자 모노 폴리시

**Files:** Modify `frontend/src/pages/Performance.tsx`, `frontend/src/pages/Performance.test.tsx`, `theme.css`

- [ ] **Step 3-1: 실패 테스트** — `Performance.test.tsx`에 추가(기존 `warm` 픽스처 사용):

```tsx
it('월 잔디(성과 달력)를 렌더한다', async () => {
  vi.spyOn(api, 'fetchPerformance').mockResolvedValue(warm);
  render(<Performance />);
  await waitFor(() =>
    expect(screen.getByTestId('monthly-perf-calendar')).toBeInTheDocument(),
  );
  expect(screen.getAllByTestId('mcal-cell').length).toBeGreaterThan(0);
});
```

- [ ] **Step 3-2: 실패 확인** → FAIL
- [ ] **Step 3-3: 구현** — `Performance.tsx`:
  - import 추가: `import MonthlyPerfCalendar from '../components/MonthlyPerfCalendar';`
  - `by-regime` div 닫힘 직후(agg `</section>` 앞 또는 뒤 — 시각상 `</section>` **뒤**, `<h2>` 앞)에 삽입:
    ```tsx
    <MonthlyPerfCalendar
      curve={a.cumulative_curve}
      sampleSize={a.sample_size}
    />
    ```
  - 숫자 모노 폴리시: `agg-hit-rate`의 `{pct(a.hit_rate)}`·`(n={a.sample_size})`, by-grade/by-regime의 `{pct(...)}`·`(n=...)`를 `<span className="mono">…</span>`로 감싼다(한글 라벨은 그대로, 숫자만 모노 — textContent 불변이라 기존 단언 유지).
- [ ] **Step 3-4: 통과 + 게이트** → PASS (기존 Performance 테스트 전부 green 유지)
- [ ] **Step 3-5: Commit** — `feat(frontend): 성과 리포트에 월 잔디 통합 + 핵심 숫자 모노화`

---

### Task 4: 성과·종목 상세 패널 콘솔 폴리시

**Files:** Modify `frontend/src/styles/theme.css` (필요시 `Performance.tsx`/`StockDetail.tsx` 클래스만)

토큰이 대부분 처리했으므로 **육안 검수 후 이탈값만** 손본다(구조·testid·카피 불변). P2 착수 시점의 스냅샷을 먼저 찍어 대상 확정.

- [ ] **Step 4-1: 스냅샷** — `_shot_p2.mjs`로 종목상세(`/stock/005930`)·성과(`/performance`) 다크/라이트 4장. (성과는 API 호스트 8010만 목킹 — SPA 네비 가로채기 금지.)
- [ ] **Step 4-2: 이탈값 목록화** — 스냅샷에서 콘솔 톤과 어긋나는 것만 추린다. 후보(있으면 수정, 없으면 스킵):
  - `.agg`·`.cum-curve`·`.metric`·상세 `.sd-*` 패널 중 여전히 둥근/그림자 있는 것 → `--radius`(2px)·헤어라인으로 (대개 토큰이 이미 처리).
  - `.by-grade .ci`·`.cum-legend ■` 등 색/간격 미세.
  - 하드코딩 hex(있다면) → 토큰.
- [ ] **Step 4-3: 수정 + 재스냅샷** — 다크/라이트 재확인. 구조 변경 금지(색·간격·radius만).
- [ ] **Step 4-4: 통과 + 게이트** — 전체 vitest·tsc·build·`.js`=0.
- [ ] **Step 4-5: Commit** — `fix(frontend): 성과·종목상세 콘솔 폴리시(패널 일관성·모노)`

---

### Task 5: 최종 검수

- [ ] **Step 5-1: 전체 게이트** — `npx vitest run` · `npx tsc --noEmit` · `npx vite build` · `.js`=0
- [ ] **Step 5-2: 이모지 0 검증** — P1과 동일 grep(`LC_ALL=C.UTF-8 grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{2300}-\x{23FF}]" src --include='*.ts' --include='*.tsx' --include='*.css'`) → `✓` 외 0건
- [ ] **Step 5-3: 최종 샷 4장**(종목상세·성과 × 다크/라이트) 육안 확인 — 월 잔디·모노 숫자·헤어라인 위계.
- [ ] **Step 5-4: WORK-PLAN §5에 P2 완료 한 줄 + 계획서 체크박스 갱신 후 Commit** — `docs: 콘솔 리디자인 P2 완료 기록`

---

## 참고 — 순서 의존성·예상

| Task | 의존 | 예상 |
|---|---|---|
| 1 날짜 유틸 | — | 15분 |
| 2 월 잔디 컴포넌트 | 1 | 40분 |
| 3 성과 통합·모노 | 2 | 25분 |
| 4 상세·성과 폴리시 | 0 | 30분 |
| 5 검수 | 전부 | 20분 |

P3(모션 3종·빈 상태·모바일 과밀)은 P2 완료 후 별도 계획.
