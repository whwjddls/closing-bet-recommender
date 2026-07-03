# 종가베팅 콘솔 리디자인 P1 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 스펙 `docs/superpowers/specs/2026-07-04-console-redesign-design.md`의 P1 — 디자인 시스템(토큰·폰트·아이콘) 교체 + 보드 전체를 "터미널 스킨 + 우리말 보이스"로 리스킨 + 신규 패널 2개(오늘의 깔때기, 내 전략의 달력).

**Architecture:** 기존 컴포넌트가 전부 CSS 커스텀 프로퍼티(토큰)를 쓰므로, 리스킨의 뼈대는 ① `:root` 토큰 값 교체(색·radius·폰트) ② 이모지→lucide 아이콘 스윕 ③ 구조 변경 3곳(GlobalHeader 상태바화, RecTable TOP3 카드 폐지+컬럼 개편, Board 레일에 신규 패널 2개)뿐이다. 로직이 있는 것(수급 라벨 변환, 잔디 셀 파생, 깔때기 사유)은 순수 함수로 분리해 TDD.

**Tech Stack:** React18 + Vite + TS + vitest. 신규 npm: `pretendard`, `@fontsource/jetbrains-mono`, `lucide-react` (전부 로컬 번들, 외부 CDN 금지).

---

## 0. 실행 전 필독 (게이트·지뢰)

- 게이트(매 태스크): `cd frontend && npx vitest run` 전부 green · `npx tsc --noEmit`(**`tsc -b` 절대 금지** — src에 .js 뱉는 사고 이력) · `npx vite build` · `find src -name '*.js'` = 0
- **testid 계약**: 기존 vitest가 참조하는 `data-testid`는 살아있어야 한다. 구조가 사라지면(예: TOP3 카드) 해당 테스트를 같은 태스크 안에서 이관한다 — 삭제가 아니라 새 구조에 대한 동등 단언으로.
- 모든 기능·카피·정직성 원칙(잠정 `*`, "참고용 추천 — 주문은 안 나가요", 빈 상태 placeholder) 불변. 백엔드 무변경.
- vitest는 반드시 `frontend/` 디렉터리에서 실행(루트에서 실행하면 다른 vitest가 잡혀 "document is not defined" 폭발 — 실사고 이력).
- 시각 검수: Playwright 스크립트를 `frontend/_shot_*.mjs`로 만들어 실행 후 **반드시 삭제**(커밋 금지). dev 서버(5173)는 떠 있다고 가정, 죽어 있으면 `cd frontend && npm run dev` 백그라운드 기동.
- 수급 라벨 실측 근거(`backend/app/data/kis_client.py:309-332`): `supply_today`는 `"외인▲" | "기관▲" | "외인▲기관▲"` 또는 null. **음수(−) 방향은 백엔드에 존재하지 않는다** — 컬럼은 +계열만 표기하고 없으면 "—".

## 파일 지도

| 파일 | 역할 |
|---|---|
| Create `frontend/src/lib/supplyLabel.ts` (+test) | `"외인▲기관▲"` → `"외국인+ 기관+"` 변환(순수) |
| Create `frontend/src/lib/perfCalendar.ts` (+test) | cumulative_curve → 잔디 셀 배열 파생(순수) |
| Create `frontend/src/components/PerfHeatmap.tsx` (+test) | 내 전략의 달력 패널 |
| Create `frontend/src/components/FunnelPanel.tsx` (+test) | 오늘의 깔때기 패널 |
| Modify `frontend/src/styles/theme.css` | 토큰 전면 교체(다크/라이트) + 상태바·테이블·패널 스타일 |
| Modify `frontend/src/main.tsx` | 폰트 CSS import |
| Modify `frontend/src/components/JobButton.tsx` | `idleLabel: ReactNode`(아이콘 수용) |
| Modify `frontend/src/components/GlobalHeader.tsx` (+test) | 상태바 리스킨 + lucide |
| Modify `frontend/src/components/RunScanButton.tsx`, `NewsBadge.tsx`, `PerfSummaryCard.tsx` | 이모지 → lucide |
| Modify `frontend/src/components/RecTable.tsx` (+test) | TOP3 카드 폐지·수급/재료 컬럼·등급 색글자 |
| Modify `frontend/src/pages/Board.tsx` (+test) | 레일에 FunnelPanel·PerfHeatmap 배치 |

---

### Task 0: 의존성 + 폰트 + 토큰 교체 (다크/라이트)

**Files:** Modify `frontend/package.json`(npm으로), `frontend/src/main.tsx`, `frontend/src/styles/theme.css`

- [ ] **Step 0-1: 패키지 설치**

```bash
cd frontend && npm i pretendard @fontsource/jetbrains-mono lucide-react
```
Expected: 3개 추가, peer 경고 없음.

- [ ] **Step 0-2: 폰트 로드** — `main.tsx` 상단(theme.css import 위)에:

```tsx
import 'pretendard/dist/web/variable/pretendardvariable.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/700.css';
```

- [ ] **Step 0-3: 토큰 교체** — `theme.css`의 `:root` 색·형태 토큰을 아래 값으로 교체(기존 토큰 **이름은 유지**, 값만):

```css
:root {
  /* 콘솔 팔레트(스펙 §1.1) */
  --bg-0: #0A0C10;  --bg-1: #10141B;  --bg-2: #161B23;
  --border: #232A33;
  --text-hi: #E8EDF2;  --text-mid: #8A96A3;  --text-lo: #5C6773;
  --up: #FF5D5D;  --down: #4D8DFF;
  /* 등급·강조: 금색(--accent)로 S/경고/잠정 통합, A는 녹색 */
  --accent: #F0B429;
  --grade-s: #F0B429;  --grade-a: #3FBF6F;  --grade-b: #4D8DFF;  --grade-c: #5C6773;
  --provisional: #F0B429;  --confirmed: #3FBF6F;  --risk: #FF5D5D;
  --regime-go: #3FBF6F;  --regime-hold: #F0B429;  --regime-off: #FF5D5D;
  /* 형태: 둥근 카드 폐지 */
  --radius: 2px;  --radius-sm: 2px;  --radius-lg: 2px;
  --shadow-card: none;  --shadow-pop: 0 8px 24px rgba(0,0,0,.5);
  --grad-top: #10141B;  --border-hover: #3A4552;
  /* 폰트 스택 */
  --font-sans: 'Pretendard Variable', Pretendard, -apple-system, 'Malgun Gothic', sans-serif;
  --font-mono: 'JetBrains Mono', Consolas, 'SF Mono', monospace;
  /* 잔디 셀 */
  --cell-win: #A83438;  --cell-loss: #2B5BB8;  --cell-skip: #232A33;
}
```

주의: 기존 `:root`에 있는 **여기 없는 토큰들(up-bg, grade-*-bg, 틴트 등)은 콘솔 팔레트에 맞는 저채도 값으로 함께 조정**한다 — 원칙: 배경 틴트는 `색상 12% 알파` 수준(`rgba(255,93,93,.10)` 등).

- [ ] **Step 0-4: 라이트 테마("종이 터미널") 값 확정 기록** — `:root[data-theme='light']` 블록을:

```css
:root[data-theme='light'] {
  --bg-0: #F2F0EB;  --bg-1: #FBFAF7;  --bg-2: #ECE9E2;
  --border: #D8D4CA;
  --text-hi: #1E232B;  --text-mid: #5A626E;  --text-lo: #98A0AB;
  --up: #D93843;  --down: #2B62D9;
  --accent: #B7791F;
  --grade-s: #B7791F;  --grade-a: #1F8A4C;  --grade-b: #2B62D9;  --grade-c: #98A0AB;
  --provisional: #B7791F;  --confirmed: #1F8A4C;  --risk: #C22F39;
  --regime-go: #1F8A4C;  --regime-hold: #B7791F;  --regime-off: #C22F39;
  --shadow-card: none;  --shadow-pop: 0 8px 24px rgba(30,35,43,.15);
  --grad-top: #FBFAF7;  --border-hover: #B9B3A5;
  --cell-win: #C9575C;  --cell-loss: #5B82D9;  --cell-skip: #DDD9CF;
}
```
(그 외 라이트 전용 틴트도 종이 톤 저채도로 함께 조정.)

- [ ] **Step 0-5: 폰트 적용** — `theme.css`의 `body`/`.mono` 규칙:

```css
body { font-family: var(--font-sans); ... }
.mono, td.num, .exp-return { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
```

- [ ] **Step 0-6: 게이트 + 샷** — `npx vitest run && npx tsc --noEmit && npx vite build`; Playwright로 보드 다크/라이트 풀샷 → **둥근 카드가 사각·헤어라인으로, 숫자가 모노로 바뀌었는지** 눈으로 확인(틴트 깨진 곳 이 단계에서 수정).

- [ ] **Step 0-7: Commit** — `feat(frontend): 콘솔 디자인 토큰·폰트(Pretendard/JetBrains Mono) 기반 교체`

---

### Task 1: 수급 라벨 변환 (TDD)

**Files:** Create `frontend/src/lib/supplyLabel.ts`, `frontend/src/lib/supplyLabel.test.ts`

- [ ] **Step 1-1: 실패 테스트**

```ts
import { describe, it, expect } from 'vitest';
import { formatSupplyToday } from './supplyLabel';

describe('formatSupplyToday', () => {
  it('백엔드 잠정 라벨을 풀네임으로 변환한다(축약 금지 — 사용자 요구)', () => {
    expect(formatSupplyToday('외인▲기관▲')).toBe('외국인+ 기관+');
    expect(formatSupplyToday('외인▲')).toBe('외국인+');
    expect(formatSupplyToday('기관▲')).toBe('기관+');
  });
  it('라벨 없음(null)은 —', () => {
    expect(formatSupplyToday(null)).toBe('—');
    expect(formatSupplyToday(undefined)).toBe('—');
  });
  it('미지의 포맷은 가공하지 않고 원문 그대로(정직성)', () => {
    expect(formatSupplyToday('연기금▲')).toBe('연기금▲');
  });
});
```

- [ ] **Step 1-2: 실패 확인** — `npx vitest run src/lib/supplyLabel.test.ts` → 모듈 없음 FAIL

- [ ] **Step 1-3: 구현**

```ts
// 백엔드 잠정 수급 라벨("외인▲기관▲" — kis_client.get_provisional_flows, +방향만 존재)을
// 풀네임으로 변환. 미지 포맷은 가공 없이 원문(정직성 — 추측 금지).
const KNOWN: Record<string, string> = {
  '외인▲기관▲': '외국인+ 기관+',
  '외인▲': '외국인+',
  '기관▲': '기관+',
};

export function formatSupplyToday(label: string | null | undefined): string {
  if (!label) return '—';
  return KNOWN[label] ?? label;
}
```

- [ ] **Step 1-4: 통과 확인** → PASS
- [ ] **Step 1-5: Commit** — `feat(frontend): 수급 잠정 라벨 풀네임 변환(외국인+/기관+)`

---

### Task 2: 잔디 셀 파생 (TDD)

**Files:** Create `frontend/src/lib/perfCalendar.ts`, `frontend/src/lib/perfCalendar.test.ts`

- [ ] **Step 2-1: 실패 테스트**

```ts
import { describe, it, expect } from 'vitest';
import { deriveHeatmapCells } from './perfCalendar';

const curve = [
  { date: '2026-06-01', cum: 0.01 },   // 첫 점: cum 자체가 증분(스펙 규칙)
  { date: '2026-06-02', cum: 0.005 },  // 증분 -0.005 → loss
  { date: '2026-06-04', cum: 0.02 },   // 증분 +0.015 → win (6/3은 곡선에 없음 → skip)
];

describe('deriveHeatmapCells', () => {
  it('일별 증분 부호로 win/loss, 곡선에 없는 날은 skip', () => {
    const cells = deriveHeatmapCells(curve, ['2026-06-01', '2026-06-02', '2026-06-03', '2026-06-04']);
    expect(cells).toEqual([
      { date: '2026-06-01', kind: 'win', delta: 0.01 },
      { date: '2026-06-02', kind: 'loss', delta: -0.005 },
      { date: '2026-06-03', kind: 'skip', delta: null },
      { date: '2026-06-04', kind: 'win', delta: 0.015 },
    ]);
  });
  it('증분 0은 skip 취급(승도 패도 아님)', () => {
    const flat = [{ date: '2026-06-01', cum: 0.01 }, { date: '2026-06-02', cum: 0.01 }];
    expect(deriveHeatmapCells(flat, ['2026-06-02'])[0].kind).toBe('skip');
  });
  it('빈 곡선 → 전부 skip', () => {
    expect(deriveHeatmapCells([], ['2026-06-01'])[0].kind).toBe('skip');
  });
});
```

- [ ] **Step 2-2: 실패 확인** → 모듈 없음 FAIL
- [ ] **Step 2-3: 구현**

```ts
// 성과 잔디(내 전략의 달력) 셀 파생 — /performance aggregate.cumulative_curve 기반.
// 스펙 §2.1: 증분>0 win(빨강)·<0 loss(파랑)·곡선에 없는 날/증분0 skip(회색).
// 첫 점 규칙: cum[0] 자체를 그날의 증분으로 취급.
export type HeatCellKind = 'win' | 'loss' | 'skip';
export interface HeatCell { date: string; kind: HeatCellKind; delta: number | null; }
interface CurvePoint { date: string; cum: number; }

export function deriveHeatmapCells(curve: CurvePoint[], dates: string[]): HeatCell[] {
  const deltaByDate = new Map<string, number>();
  curve.forEach((p, i) => {
    deltaByDate.set(p.date, i === 0 ? p.cum : p.cum - curve[i - 1].cum);
  });
  return dates.map((date) => {
    const delta = deltaByDate.get(date);
    if (delta === undefined || delta === 0) return { date, kind: 'skip' as const, delta: delta ?? null };
    return { date, kind: delta > 0 ? ('win' as const) : ('loss' as const), delta };
  });
}
```

- [ ] **Step 2-4: 통과 확인** → PASS
- [ ] **Step 2-5: Commit** — `feat(frontend): 성과 잔디 셀 파생 로직(perfCalendar)`

---

### Task 3: PerfHeatmap 패널

**Files:** Create `frontend/src/components/PerfHeatmap.tsx`, `frontend/src/components/PerfHeatmap.test.tsx`; Modify `theme.css`

동작: `cachedFetch('performance', fetchPerformance)` → 최근 42일(달력일 기준, KST) 날짜열 생성 → `deriveHeatmapCells` → 7열 그리드 잔디. 헤더 `내 전략의 달력` + 우측 `성공 n · 실패 m`. 표본 0(`aggregate.sample_size === 0`) 또는 fetch 실패 → "아직 기록이 없어요" — **빈 상태는 `perf-heatmap` 컨테이너 안에 `perf-heatmap-empty`로 렌더**(컨테이너 testid 상시 존재 → Board 테스트가 fetch 결과와 무관하게 안정). 전체가 `/performance` 링크(`Link`). 날짜열은 `kstToday()` 기반(자정 버그 방지 — `lib/date.ts` 재사용).

- [ ] **Step 3-1: 실패 테스트** — `PerfSummaryCard.test.tsx`의 목 구조를 재사용(같은 PerformanceResponse 픽스처 패턴, MemoryRouter 래핑):
  - 곡선 3점(승2·패1) → `heat-cell` 42개 렌더 + `data-kind` win/loss 셀 존재 + 카운트 문구
  - sample_size 0 → `perf-heatmap-empty` "아직 기록이 없어요"
  - fetch 실패 → 동일 빈 상태
- [ ] **Step 3-2: 실패 확인** → FAIL
- [ ] **Step 3-3: 구현** — 컴포넌트(약 80줄) + CSS:

```css
.perf-heatmap { display:block; background:var(--bg-1); border:1px solid var(--border); border-radius:var(--radius); padding:10px 12px; color:inherit; }
.ph-head { display:flex; justify-content:space-between; font-size:11px; color:var(--text-mid); margin-bottom:6px; }
.ph-grid { display:grid; grid-template-columns:repeat(7,1fr); gap:3px; }
.ph-cell { aspect-ratio:1; border-radius:1px; background:var(--cell-skip); }
.ph-cell[data-kind='win'] { background:var(--cell-win); }
.ph-cell[data-kind='loss'] { background:var(--cell-loss); }
```
각 셀 `title`에 `날짜 · +0.4%` 툴팁. testid: `perf-heatmap`, `heat-cell`, `perf-heatmap-empty`.
- [ ] **Step 3-4: 통과 + 게이트** → PASS
- [ ] **Step 3-5: Commit** — `feat(frontend): 내 전략의 달력(성과 잔디) 패널`

---

### Task 4: FunnelPanel 패널

**Files:** Create `frontend/src/components/FunnelPanel.tsx`, `frontend/src/components/FunnelPanel.test.tsx`; Modify `theme.css`

props 주도(자체 fetch 없음 — Board가 이미 가진 데이터 전달): `{ universeCount: number | null; board: RecommendationsResponse | null }`.
표기 규칙(스펙 §2.1 확정):
- 데이터 로딩 전(null) → 스켈레톤 한 줄
- `data_available === false` → `후보 N → —` + 사유 "데이터 없음"
- 발행 + 추천 0 → `후보 N → 0` + 사유 "신호 통과 0 — 오늘은 관망"
- 발행 + 추천 M>0 → `후보 N → M` + 커버리지 `%`
- universeCount 0/null(프리페치 전) → 후보 자리 "—" (추측 금지)

- [ ] **Step 4-1: 실패 테스트** — 위 4규칙 각 1건 + 사유 문구 단언 (testid: `funnel-panel`, `funnel-flow`, `funnel-reason`)
- [ ] **Step 4-2: 실패 확인** → FAIL
- [ ] **Step 4-3: 구현** (약 60줄; 숫자는 `.mono` 대형, 화살표 `→` 텍스트) + 패널 CSS(PerfHeatmap과 동일 패널 규칙 재사용)
- [ ] **Step 4-4: 통과 + 게이트** → PASS
- [ ] **Step 4-5: Commit** — `feat(frontend): 오늘의 깔때기 패널 — 추천 0건인 날의 이유를 숫자로`

---

### Task 5: GlobalHeader 상태바화 + 이모지→lucide 스윕

**Files:** Modify `frontend/src/components/GlobalHeader.tsx`(+test), `JobButton.tsx`, `RunScanButton.tsx`, `NewsBadge.tsx`, `PerfSummaryCard.tsx`, `RecTable.tsx`(material-hint 아이콘만), `theme.css`

- [ ] **Step 5-1: 이모지 전수 조사** — **ts/tsx/css 전부**를 유니코드 범위로 스캔(고정 목록 금지 — 누락 실사고 방지):

```bash
cd frontend && grep -rnP "[\x{1F300}-\x{1FAFF}\x{2600}-\x{27BF}\x{2B00}-\x{2BFF}\x{2190}-\x{21FF}\x{25A0}-\x{25FF}]" src --include='*.ts' --include='*.tsx' --include='*.css'
```

결과 전부를 아래 표대로 교체(표에 없는 발견분도 같은 원칙 — 아이콘은 lucide, 의미 라벨은 텍스트). **`.ts` 데이터 라벨 변경은 해당 테스트 단언도 같은 스텝에서 수정**:

| 위치 | 현재 | 교체(lucide, 14px) |
|---|---|---|
| GlobalHeader 카운트다운 `⏱` | 텍스트 | `<Timer size={14} />` |
| GlobalHeader 배너 `⚠` | 텍스트 | `<TriangleAlert size={14} />` |
| 테마 토글 `☀️/🌙` | 텍스트 | `<Sun size={15} />/<Moon size={15} />` |
| JobButton `📥/🧮`(호출부 라벨) | 문자열 | `<Download size={14} />/<Calculator size={14} />` |
| RunScanButton `▶` | 텍스트 | `<Play size={14} />` |
| NewsBadge `📰` | 텍스트 | `<Newspaper size={12} />` |
| PerfSummaryCard `📊`(CSS ::before) | CSS | ::before 규칙 삭제, JSX에 `<ChartColumn size={14} />` |
| RecTable material-hint `🔍` | 텍스트 | `<Search size={13} />` |
| `lib/badges.ts` `'⚠희석'` 라벨(.ts 데이터) | 문자열 | 텍스트 `'희석 주의'` — **`badges.test.ts` 등 관련 단언 동시 수정** |
| `theme.css` `content:'📰'` ::before | CSS | 규칙 삭제(NewsBadge가 lucide 사용) |
| `Board.tsx` 시황 `🟢🟡🔴` | 문자열 | `<span className="mood-dot" data-mood="go/hold/off" />`(8px 원, 배경 `--regime-*`) — Board 테스트에 이모지 단언 있으면 함께 수정 |
| RecTable 헤더 `⚑`·행 `★/─` | 텍스트 | `⚑/─`는 리스크 컬럼 폐지로 소멸(Task 6), `★`는 `<Star size={11} />` |

- [ ] **Step 5-2: JobButton 시그니처** — `idleLabel: string` → `idleLabel: ReactNode` (렌더는 그대로). 기존 테스트 무변경으로 green이어야 함(문자열도 ReactNode).
- [ ] **Step 5-3: 상태바 리스킨** — GlobalHeader 마크업 구조·testid 전부 유지, CSS만 콘솔화: 1줄 고정(56px→40px), `--bg-0` 배경 + 하단 헤어라인, 로고 `종가베팅▮콘솔`(▮는 `--accent`), 요소 간 구분은 `·` 대신 얇은 세로 디바이더, **15:00 KST 이후 카운트다운에 `gh-countdown--hot` 클래스(금색+펄스 keyframe)**. 기존 urgencyClass 로직에 시각 조건만 추가.
- [ ] **Step 5-4: 테스트** — 기존 GlobalHeader 테스트 green 확인 + 신규 1건: 15:00 이후(fake timers)면 `close-countdown`에 `gh-countdown--hot` 클래스.

확정 해석: **지수(코스피/코스닥)는 상태바에 통합하지 않는다** — 기존 IndexStrip 유지(스펙 §2.1 상태바 필수 목록에 지수 없음).
- [ ] **Step 5-5: 게이트 + 샷** (다크/라이트 상단바 클립) 
- [ ] **Step 5-6: Commit** — `feat(frontend): 상태바 콘솔화 + 이모지 전면 제거(lucide 아이콘)`

---

### Task 6: RecTable 콘솔화 (구조 변경 — 신중)

**Files:** Modify `frontend/src/components/RecTable.tsx`, `frontend/src/components/RecTable.test.tsx`, `theme.css`

- [ ] **Step 6-1: 영향 조사(광범위)** — 아래 grep 결과 전부를 나열하고 이 태스크 안에서 이관(누락 금지):

```bash
cd frontend && grep -rn "top3\|exit-cta\|exit_label\|buy-price\|exp-return\|exp-close\|supply-today-badge\|col-risk\|MiniChart" src
```

- [ ] **Step 6-2: 기존 컬럼 처분표** — 컬럼 재편은 "삭제"가 아니라 아래 처분을 따른다(스펙 불변조항 #2·#3 보존):

| 기존 컬럼 | 처분 |
|---|---|
| ⚑ 리스크 | 컬럼 폐지. 행 `data-risk` 속성·리스크 행 좌측 `--risk` 보더 유지, 종목 셀 보조줄의 '희석 주의' 배지(deriveBadges)가 시각 신호 담당 |
| 현재가* | 유지(1줄째) — 잠정 `*` 마커 유지 |
| 매수 참고가 | 컬럼 폐지 → **현재가 셀 2줄째** `매수 {값}` 보조줄로 통합. testid `buy-price`와 잠정 `*` 이 보조줄에 유지 |
| 예상 마감가 | 컬럼 폐지 → 현재가 셀 3줄째 소형 텍스트 `예상 {값}` (testid `exp-close` 유지, null이면 줄 생략) |
| 다음날 아침 팔기(exit-cta) | 컬럼 폐지 → **테이블 각주 행**(colspan, testid `table-footnote`): `* 15:20 잠정 — 마감(15:30) 확정 · 기본 전략: 다음날 아침 9~10시에 팔기` (불변조항 #3 카피 보존). 참고 목표/손절은 전용 컬럼으로 이미 보존 |
| 기대(exp-return) | 참고목표 셀 안에 `+9.2%` 소형 병기(방향색, testid `exp-return` 유지) |
| 신호(배지·supply_today) | deriveBadges 배지는 종목 셀 보조줄로, supply_today는 신규 수급 컬럼으로 |
| 차트(MiniChart) | 컬럼 폐지 + **RecTable의 MiniChart import 제거**(noUnusedLocals tsc 실패 방지). 스파크는 종목 상세 존치 |
| #·등급·담기 | 유지(등급은 배지 박스 → 색 글자, testid `rec-grade` 유지) |

최종 컬럼: `# 등급 종목 현재가(3줄 복합) 참고목표(기대 병기) 참고손절 평소보다거래 수급 재료 담기` + 각주 행

- [ ] **Step 6-3: 실패 테스트 먼저 수정** — RecTable.test에서(전부 이 스텝에서):
  - `top3-card` 단언 → 상위 3행 `rec-row[data-top3="true"]` 3개 + 1위 행 `row-rank-marker` 존재로 대체
  - "TOP3 카드마다 재료 배지" → "모든 행의 재료 컬럼에 NewsBadge"(`news-badge`+`news-badge-none` 합 = 행 수)
  - exit-cta/'오전 VWAP' 단언(≈:88-92) → `table-footnote`가 "아침 9~10시" 카피 포함 단언으로 대체
  - buy-price 잠정 `*` 단언(≈:101-108) → 현재가 셀 보조줄 `buy-price` 단언으로 이관(`*` 유지 확인)
  - supply-today-badge 원문 단언(≈:175-191) → 수급 셀이 `외국인+ 기관+` + `잠정` 태그 표시로 교체(testid `supply-today-badge` 유지)
  - 신규: `supply_today` 없음 → `—`
- [ ] **Step 6-4: 실패 확인** → FAIL
- [ ] **Step 6-5: 구현**
  - TOP3 카드 블록(`rec-top3-cards` JSX)·관련 CSS(`.top3-card`·`.t3-*`) 삭제. 행 하이라이트 `.rec-top3 { border-left:2px solid var(--grade-s); background: rgba(240,180,41,.05); }` + 1~3위 행 첫 컬럼 `<span data-testid="row-rank-marker"><Star size={11} /></span>`
  - 처분표대로 셀 구성. 수급 셀: `formatSupplyToday(r.supply_today)` + `잠정` 미니 태그 + 기존 툴팁 문구, `+` 포함 시 `dir-up` 색
  - 재료 셀: `<NewsBadge ticker={r.ticker} />` 전 행. **첫 렌더 시 최대 30행 병렬 fetchNews 버스트 발생을 인지하고 허용** — 실추천은 보통 소수·백엔드 /news는 graceful 빈 응답·cachedFetch 5분이 정렬/필터 remount 재조회를 흡수. 문제가 실측되면 후속으로 상위 10행만 자동 조회(이번 스코프 아님)
  - 테이블 CSS: 헤어라인 행 구분, 셀 padding 축소, 숫자 셀 `--font-mono`
- [ ] **Step 6-6: 통과 + 전체 게이트 + 샷**(추천 있는 상태가 필요하므로 vitest 픽스처 스토리는 테스트로, 실화면은 빈 보드라도 헤더/깔때기 확인)
- [ ] **Step 6-7: Commit** — `feat(frontend): 추천 테이블 콘솔화 — TOP3 행마커·수급 풀네임·재료 컬럼`

---

### Task 7: Board 레일 재배치 + 위젯 패널 통일

**Files:** Modify `frontend/src/pages/Board.tsx`(+test), `theme.css`

- [ ] **Step 7-1: 실패 테스트** — Board.test의 `setup()`에 `vi.spyOn(api, 'fetchPerformance').mockResolvedValue(표본0 픽스처)` 추가(현재 미목 상태라 실 fetch 거부에 의존 중 — 결정성 확보), 그 후 신규 단언: 렌더 시 `funnel-panel`과 `perf-heatmap`이 레일에 존재(universe·recommendations는 기존 목).
- [ ] **Step 7-2: 구현** — 보드 레일 순서: `FunnelPanel`(최상단) → `PerfSummaryCard` → `PerfHeatmap` → 기존 위젯들. FunnelPanel엔 Board가 이미 들고 있는 `universe.rows.length`·`board` 전달. 위젯 패널 통일 CSS: 위젯 컨테이너 셀렉터 그룹에 패널 규칙(사각·헤어라인·제목줄 11px `--text-mid`) 일괄 적용 — 위젯별 개별 radius/그림자 규칙은 토큰이 이미 처리하므로 **이탈값만 정리**.
- [ ] **Step 7-3: 통과 + 전체 게이트** 
- [ ] **Step 7-4: Commit** — `feat(frontend): 보드 레일 재배치 — 깔때기·잔디 패널 배치`

---

### Task 8: 최종 검수

- [ ] **Step 8-1: 전체 게이트** — `npx vitest run`(전부) · `npx tsc --noEmit` · `npx vite build` · `.js` 0
- [ ] **Step 8-2: Playwright 풀샷 4장 + 이모지 0 검증** — 보드/성과 × 다크/라이트 (`_shot_console.mjs` 작성→실행→삭제). 이모지 잔존은 Step 5-1의 **동일한 유니코드 범위 grep이 0건**임을 명령으로 검증. 눈 검수: 모노 숫자 정렬, 헤어라인 위계, 라이트(종이 터미널) 대비, 잔디/깔때기 패널.
- [ ] **Step 8-3: 스크린샷을 보고 어색한 상위 3개를 즉석 수정** — 허용 범위: 색 틴트·간격·**잔존 이모지 제거(관련 테스트 수정 포함)**. 구조 변경만 금지.
- [ ] **Step 8-4: WORK-PLAN §5에 한 줄 기록 + 계획서 체크박스 갱신 후 Commit** — `docs: 콘솔 리디자인 P1 완료 기록`

---

## 참고 — 순서 의존성·예상

| Task | 의존 | 예상 |
|---|---|---|
| 0 토큰·폰트 | — | 40분 |
| 1 수급 라벨 | — | 15분 |
| 2 잔디 파생 | — | 20분 |
| 3 PerfHeatmap | 2 | 40분 |
| 4 FunnelPanel | — | 30분 |
| 5 상태바+아이콘 | 0 | 50분 |
| 6 RecTable | 0,1 | 60분 |
| 7 Board 배치 | 3,4 | 30분 |
| 8 검수 | 전부 | 30분 |

P2(종목 상세·성과 리포트 리스킨)·P3(모션·빈상태·모바일)는 P1 완료 후 별도 계획.
