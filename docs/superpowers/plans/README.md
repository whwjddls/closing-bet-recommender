# 구현 플랜 인덱스 — closing-bet-recommender

승인된 설계: [`../specs/2026-06-30-closing-bet-recommender-design.md`](../specs/2026-06-30-closing-bet-recommender-design.md) (v3.1)
아키텍처: [`../specs/2026-06-30-architecture.md`](../specs/2026-06-30-architecture.md)

5개 서브시스템으로 분할. **순차 의존(1→2→3·4→5)** — 각 플랜은 독립적으로 빌드·테스트 가능.

| # | 플랜 | 의존 | 핵심 |
|---|---|---|---|
| 01 | [데이터 레이어 & 저장소](2026-06-30-01-data-layer.md) | 없음(기반) | BrokerDataAdapter·KIS/pykrx/DART 클라이언트·SQLite 스키마·매핑 |
| 02 | [추천 엔진](2026-06-30-02-engine.md) | 01 | 신/거/수급/veto 신호·시황 4상태 게이트·core/final·가격규칙·파이프라인 |
| 03 | [백테스트 & 검증](2026-06-30-03-backtest.md) | 01,02 | 순수 pandas·룩어헤드/생존편향 가드·rank-IC 직교화·수용기준 |
| 04 | [API & 스케줄러](2026-06-30-04-api-scheduler.md) | 01,02 (03은 /backtest) | FastAPI 라우터·15:20 런·익일 오전VWAP 채점·KRX 캘린더·작업스케줄러 |
| 05 | [프론트엔드](2026-06-30-05-frontend.md) | 04(API) | 추천보드·종목상세·성과추적·7컴포넌트·vitest+RTL |

실행: 각 플랜은 `superpowers:subagent-driven-development` 또는 `superpowers:executing-plans`로 Task 단위 진행.
