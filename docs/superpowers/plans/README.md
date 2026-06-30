# 구현 플랜 인덱스 — closing-bet-recommender

승인된 설계: [`../specs/2026-06-30-closing-bet-recommender-design.md`](../specs/2026-06-30-closing-bet-recommender-design.md) (v3.1)
아키텍처: [`../specs/2026-06-30-architecture.md`](../specs/2026-06-30-architecture.md)

> **먼저 읽기:** [`2026-06-30-00-interface-contracts.md`](2026-06-30-00-interface-contracts.md) — 서브시스템 경계 계약의 **단일 진실원천**. 플랜 본문과 충돌 시 **00이 우선**. (저장소 ORM·데이터레이어 함수·오케스트레이터·BacktestResult·API 응답 스키마)

5개 서브시스템으로 분할. **순차 의존(1→2→3·4→5)** — 각 플랜은 독립적으로 빌드·테스트 가능. 모든 플랜 상단에 "계약 우선" 배너가 00을 가리킴.

| # | 플랜 | 의존 | 핵심 |
|---|---|---|---|
| 00 | [인터페이스 계약](2026-06-30-00-interface-contracts.md) | — | 경계 계약 단일 진실원천(우선순위 최상) |
| 01 | [데이터 레이어 & 저장소](2026-06-30-01-data-layer.md) | 없음(기반) | SQLAlchemy ORM·KIS/pykrx/DART 클라이언트·매핑·헬스체크 |
| 02 | [추천 엔진](2026-06-30-02-engine.md) | 01 | 신/거/수급/veto 신호·시황 4상태 게이트·core/final·가격규칙·순수 run_pipeline |
| 03 | [백테스트 & 검증](2026-06-30-03-backtest.md) | 01,02 | 순수 pandas·룩어헤드/생존편향 가드·rank-IC 직교화·`run_backtest` 래퍼 |
| 04 | [API & 스케줄러](2026-06-30-04-api-scheduler.md) | 01,02 (03은 /backtest) | FastAPI·`orchestrate_run`·15:20 런·익일 오전VWAP 채점·MODELED RVOL 생산자·캘린더 |
| 05 | [프론트엔드](2026-06-30-05-frontend.md) | 04(API §5 스키마) | 추천보드·종목상세·성과추적·7컴포넌트·vitest+RTL |

## 리뷰 이력
- 1차(병렬 작성 직후): 교차일관성·TDD·시퀀싱·스펙완전성 4차원 적대적 리뷰 → blocker 8/major 12.
- 진단: **플랜 내부 TDD 우수, 결함은 전부 경계 계약**(저장소 기술·run_pipeline·데이터레이어 함수·BacktestResult·API↔프론트 스키마) + 실제 버그 1건(rvol 상수).
- 조치: 단일 진실원천 `00` 신설로 경계 계약 확정 + 각 플랜 "계약 우선" 배너 + B3(rvol 0.834044/0.933618) 직접 교정.

실행: 각 플랜은 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`로 Task 단위 진행. **반드시 00을 먼저 읽고**, 충돌 시 00을 따른다.
