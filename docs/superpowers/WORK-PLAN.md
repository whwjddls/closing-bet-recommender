# 작업계획 (핸드오프) — closing-bet-recommender

작성: 2026-07-03 · 기준 커밋 `a93d119` (main, origin+32) · **다른 도구/세션에서 개발을 이어받기 위한 상세 계획서**

---

## 0. 프로젝트 스냅샷

- **무엇**: 매 거래일 15:20(마감 직전) 종가베팅 추천 대시보드. 오버나잇 캡처(종가 매수 → 익일 오전 9~10시 VWAP 매도). **추천 전용, 주문 없음.**
- **점수 모델**: `final = s_신(52주 신고가 근접) × rvol_confirm(거래량 확인) × regime(장 분위기 0/0.5/1) × supply_tilt(수급 0.8~1.2) × veto(희석 공시 0/1)`. 등급 S/A/B/C = core(레짐 제외) 기준.
- **스택**: FastAPI + SQLAlchemy(SQLite `backend/state/cbr.sqlite`) / React18 + Vite + TS(다크 트레이딩 테마) / pykrx(KRX 로그인) + KIS OpenAPI + DART.
- **테스트 게이트(전부 green 상태)**: `cd backend && .venv/Scripts/python -m pytest -q`(약 310+) · `cd frontend && npm test`(146) · `npx tsc --noEmit` · `find frontend/src -name '*.js'`=0 (tsc는 반드시 `--noEmit`, `tsc -b` 금지 — src에 .js 뱉는 사고 이력).
- **실행**:
  ```
  backend:  .\backend\.venv\Scripts\python.exe -m uvicorn --app-dir backend app.main:app --port 8010 --reload
  frontend: cd frontend && npm run dev   (5173, VITE_API_BASE는 frontend/.env.local=8010)
  ```
- **크리덴셜**(`backend/.env`, git 제외 — 자동 로드됨): `KRX_ID/KRX_PW`(pykrx 로그인, data.krx.co.kr 무료계정), `KIS_APP_KEY/SECRET/BASE_URL/ACCOUNT`, `DART_API_KEY`. 전부 채워져 있고 실검증됨.
- **문서 지도**: 계약 정본 `docs/superpowers/plans/2026-06-30-00-interface-contracts.md`(**충돌 시 항상 우선**) · 설계 `specs/2026-06-30-closing-bet-recommender-design.md` · 아키텍처 `specs/2026-06-30-architecture.md` · UI 방향 `2026-07-01-UI-DESIGN-PROPOSAL.md` · 통합수정 이력 `REMEDIATION-STATUS.md`.

---

## 1. 🔴 중단된 진행중 과업 4건 (착수 직전 상태 — 최우선)

> 직전 세션에서 스펙 확정 후 에이전트 중단됨. 코드 변경 없음(트리 클린). 아래 스펙 그대로 구현하면 됨. 전부 **frontend만** (backend 계약은 완료·커밋됨).

### 1-1. 스캔 버튼 장시간 실행 UX (버그)
- **증상**: [지금 스캔 실행] 클릭 후 "스캔 중"이 안 끝나는 것처럼 보임. 실제로는 장전 캐시 없으면 **3~10분 걸리는 정상 동작**인데 경과 표시가 없음. 또 페이지 이동하면 버튼 상태 유실.
- **백엔드 준비 완료**: `GET /run/status` → `{running, last_result, last_error, finished_at, started_at: string|null, elapsed_sec: number|null}` (커밋 `d1a343f` 근방).
- **구현**(`frontend/src/components/GlobalHeader.tsx`, `src/api/client.ts`):
  - client 타입에 `started_at`/`elapsed_sec` 추가.
  - 버튼 **mount 시 /run/status 동기화** — 이미 running이면 "스캔 중" 복원+폴링(3s) 재개.
  - 표시: "**스캔 중 · N분 M초**"(elapsed_sec 기준, 로컬 1초 틱) + 보조 "장전 캐시가 없으면 3~10분 걸릴 수 있어요".
  - running=false 전환: 폴링 중지(useEffect cleanup, interval 누수 금지) + 결과(OK="추천 생성 완료 ✓"/UNPUBLISHED="오늘은 추천을 만들지 못했어요"/SKIPPED="오늘은 휴장일이에요"/last_error) + 보드 refetch.
  - vitest: mount 복원 · elapsed 표시 · 종료 시 중지.

### 1-2. 화면 전환 시 지표 사라짐 (버그)
- **원인**: 위젯이 remount마다 재조회하고 실패/빈 응답이 기존 데이터를 **덮어씀**. 특히 스캔 실행 중엔 KIS/KRX를 스캔이 점유해 위젯 재조회가 실패함.
- **구현**: `frontend/src/lib/dataCache.ts` 신규 — `cachedFetch<T>(key, fetcher, ttlMs=60000)`: 캐시 있으면 **즉시 반환**(만료 시 백그라운드 갱신), fetcher **실패/빈배열이면 기존 캐시 유지**(빈 값으로 절대 덮지 않음). `/market /highs /calendar /disclosures /universe /reminder /performance` 위젯 fetch 전부 이 캐시 경유로 전환.
  - vitest: 실패 시 기존값 유지 · 재mount 즉시 캐시 표시.

### 1-3. "어제 성과" 카드 — 한 화면 통합 (기능)
- 보드 우측 위젯 스택 **최상단**에 컴팩트 카드: `/performance`의 aggregate → **성공률(다음날 아침 기준) N% (n=표본) · 평균 아침 수익률** + 최근 픽 결과 1~2줄(종목명 ✅/❌). 클릭 → `/performance` 이동. 표본 0 → "아직 기록이 없어요". (`src/components/PerfSummaryCard.tsx` 신규 + Board 배치 + vitest)

### 1-4. 라이트/다크 테마 토글 (기능)
- `frontend/src/styles/theme.css`: 현행 다크 토큰을 `:root` 기본으로 두고 `:root[data-theme='light']` 오버라이드 세트 추가 — 라이트: bg `#F4F6FA`·카드 `#FFFFFF`·hover `#EEF2F7`·보더 `#E2E8F0`·텍스트 `#1A202C/#4A5568/#94A3B8`·**상승 `#E5484D`/하락 `#2563EB`**(한국 관례 유지)·등급 S `#B7791F`/A `#15803D`/B `#2563EB`/C `#94A3B8`·잠정 앰버 `#B45309`·레짐 GO `#15803D`/보통 `#B45309`/OFF `#DC2626`. 틴트 배경(up-bg 등)은 연한 파스텔.
- GlobalHeader에 ☀️/🌙 토글 → `document.documentElement.dataset.theme` + localStorage persist, 기본 dark.
- **컴포넌트 하드코딩 hex 스윕**(라이트에서 안 보이는 색): StockDetail priceLine(`'#c00'`,`'#08c'`,`'#999'` — src/pages/StockDetail.tsx:70~75), 스파크/차트 색 등 → 토큰 또는 양테마 무난색으로.
- vitest: 토글 전환+persist.

---

## 2. 🟡 검증 대기 — 15:20 라이브 런 (코드 완성, 실전 미확인)

**절차**(장중, 이상적으론 15:20~15:30):
1. (선택, 강력 권장) 장전에 프리페치: `cd backend && .venv/Scripts/python -c "from dotenv import load_dotenv; load_dotenv(); from app.scheduler.premarket import run_premarket; run_premarket()"` — D-1 거래대금 상위 200 유니버스 캐시. **이거 없으면 스캔이 라이브 톱60 폴백 + 종목당 OHLCV 순차조회로 3~10분.**
2. UI [지금 스캔 실행] 클릭 (또는 `POST localhost:8010/run`).
3. 기대: `OK` → 보드에 실추천 · 15:30 전이면 유의미. `UNPUBLISHED` → 사유 확인(커버리지<70%/KIS 미수신).
4. **밤에 이미 검증된 것**: KRX 로그인, volume-rank(거래대금 톱30×2), 수급(외인+기관 합산), 오버나잇 갭, /market·/stock·/disclosures 실데이터. **미검증**: 신규 TR 5종(신고가근접·VI·상한가·예상마감가·당일가집계) 실응답 필드, 장중 시세 파이프라인 end-to-end. 필드 불일치 나오면 해당 파서만 고치면 됨(관대 파싱으로 작성돼 있음).

**주의**: KIS 접근토큰은 **1분 1회 발급 제한** — `state/kis_token.json` 파일 공유 캐시가 있어 평시엔 문제없으나, 캐시 삭제/계정 변경 직후엔 1분 대기.

---

## 3. 🟢 백로그 (우선순위순)

| P | 항목 | 상세 |
|---|---|---|
| P1 | **Windows 작업스케줄러 등록** | `backend/deploy/` 스크립트 이미 존재(Task 11 산출). 장전 프리페치(08:30)·15:20 런·익일 채점(10:05) 3잡 등록해 버튼 없이 자동화. schtasks 등록 후 1주 관찰 |
| P1 | **익일 채점 사이클 실검증** | scoring_job이 확정종가+오전VWAP(KIS 분봉)으로 채점 → 성과 리포트 채워지는지. 첫 실추천 다음날 확인 |
| P2 | S6 스캐너 퍼널 | 유니버스→최종30 단계별 탈락 사유(퍼널 뷰) + "거의 들 뻔한 종목". 파이프라인이 단계별 카운트를 RunResult에 실어야 함(orchestrator 확장) |
| P2 | psearch 조건검색 연동 | 사용자가 HTS에서 조건식 저장 필요(예: "52주고가 97% 이내+RVOL 2배") → `psearch_title/result` TR로 전 종목 서버 스캔. 후보풀의 완성형 |
| P2 | KIS 지수코드 확정 | inquire-index-price의 KOSPI 코드가 애매(0001=7648?, 0002=8432?) — 장중 실값과 대조해 확정. 현재 레짐은 pykrx 단일소스라 **동작엔 지장 없음** |
| P3 | 실시간 오전 VWAP 리마인더 | ReminderWidget "추정 미연동" → 장중 KIS 분봉으로 실시간 추정 |
| P3 | 루트 README + .env.example 보강 | 설치→키 발급→실행→15:20 운영 가이드. (.env.example은 있음, README 없음) |
| P3 | GitHub push | 로컬 main이 **origin+32** — push 필요. `git push origin main` |
| P3 | 모바일 반응형 정리 | Playwright mobile 샷 기준 과밀 구간 조정 |

---

## 4. ⚠️ 운영 노트 · 알려진 이슈 (신규 개발자가 밟기 쉬운 지뢰)

1. **KIS 토큰 1분 1회**: 모든 KisClient가 `state/kis_token.json` 공유(만료 24h, 발급실패 시 캐시 fail-soft). 새 KIS 코드 짤 때 **클라이언트 직접 생성 금지** — `build_default_client()`/`build_live_adapter()` 경유.
2. **pykrx는 KRX 로그인 필수**(1.2.8+): env `KRX_ID/KRX_PW`. 로그인 로그가 stdout에 찍힘(무해).
3. **pykrx 시계열 OHLCV엔 `거래대금` 컬럼 없음**(종가×거래량 파생 사용). 투자자별 컬럼명은 `외국인합계/기관합계`. **실 API 필드는 반드시 실측 후 사용** — 목 기반 개발로 3번 깨진 이력.
4. **DB 스키마 변경 시**: `init_db()`가 누락 컬럼 자동 ALTER(경량 마이그레이션) — 모델에 컬럼 추가해도 기존 DB 안 깨짐. **nullable로만 추가**할 것.
5. **API 500 = 프론트 "Failed to fetch"**: FastAPI 미처리 예외엔 CORS 헤더가 안 붙어 브라우저가 network error로 표시. 500 의심되면 curl로 직접 확인.
6. **날짜는 반드시 KST 유틸**: `toISOString()`은 UTC라 자정~09시에 어제 날짜 나옴(수정된 버그). 프론트 날짜 계산은 kstToday 패턴 준수.
7. **UNPUBLISHED는 정상 게이트**: 데이터 미수신/커버리지<70%/레짐 0이면 의도적으로 미발행. 에러 아님.
8. **전략 자체는 미검증**: 백테스트 go/no-go(rank-IC>0, t>2, 벤치 초과) 통과 전 가중치 상향 금지(설계 §2·§7). 추천은 참고용.
9. **밤/휴장 시간 개발**: KIS 시세는 정체값, 신규 TR 일부는 빈 응답 — "데이터 없음(장중 조회)" placeholder가 정상.
10. **데모 데이터 금지**(사용자 방침): 검수 필요 시 임시 시드 → 즉시 삭제. `backend/state/cbr.sqlite` 삭제 = 완전 초기화(재시작 시 재생성).

---

## 5. 참고 — 완료된 것 (요약)

- 백엔드: 데이터레이어(pykrx/KIS/DART, 어댑터) · 엔진(신호 5종+파이프라인) · 백테스트(rank-IC/직교화/수용기준) · API 13종(`/recommendations /stock /performance /reminder /universe /market /calendar /disclosures /highs /news /run /run/status /health /backtest`) · 스케줄러(장전/15:20/채점) · 오케스트레이터(D-1 200 풀+RVOL 생산자) · KIS TR 9종 · 자동 마이그레이션 · 토큰 파일 캐시.
- 프론트: 다크 콕핏 전면 리디자인 + 초보자 친화 카피 전면 교체("오늘 장 분위기/평소보다 거래 N배/다음날 아침 9~10시 팔기") · 위젯 12종 · 스캔 실행 버튼 · Playwright 시각 QA 2라운드(16건 발견·수정, KST 버그 포함) · 참고 조회 모드.
- 품질: 적대적 리뷰 누적 6회(설계3·플랜1·구현2), 통합 결함 20+4+1건 수정, 테스트 백엔드 310+·프론트 179.
- 스크린샷 스크립트: 세션 스크래치패드 `ui_shots.mjs` (frontend에 복사 후 `node _ui_shots.mjs`, playwright devDep 설치됨).
- 신고가 위젯 빈 화면 수정: /highs ETF 필터(KRX 교차검증) · 참고 조회 실명 · 차트 테마/빈데이터 가드 (2026-07-03)
