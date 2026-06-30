# 종가베팅 추천 시스템 — 아키텍처 구조

> 추천/리서치 전용(주문 없음). 매 거래일 15:20 KST(특수세션=마감−10분) 실행, 익일 상승 후보 최대 30개 랭킹.

---

## 0. 한눈에 보는 전체 구조

```
┌──────────────────── 데이터 소스 ─────────────────────┐
│ pykrx     EOD OHLCV · D-1 외인/기관수급 · 지수이력   [FINAL]       │
│ KIS API   15:20 잠정시세 · 거래대금랭킹 · 지수레벨    [PROVISIONAL] │
│ DART API  희석성 공시(유증/CB/BW/EB)                  [VETO]        │
└───────────────────────────┬──────────────────────────┘
              BrokerDataAdapter + 중앙 인덱스/티커 매핑(코드충돌 흡수)
                            ▼
┌──────────────────── 추천 엔진 (Python) ───────────────┐
│ ①후보풀 → ②정적위생 → ③라이브조회(~260) → ④동적위생  │
│ → 시황게이트(0/0.5/1) → 신호[신·거·수급·veto]          │
│ → core → final → top30 → 가격규칙(매수/청산/목·손)     │
└───────────────────────────┬──────────────────────────┘
                  write: SQLite + state/recommendations/YYYY-MM-DD.json
                            ▼
┌──────────────────── API (FastAPI) ────────────────────┐
│ /recommendations/{date} · /stock/{code} · /performance │
│ /backtest · /universe · /health                        │
└───────────────────────────┬──────────────────────────┘
                       REST/JSON (클라이언트 정렬·필터)
                            ▼
┌──────────────────── 프론트 (React/Vite) ──────────────┐
│ 추천보드 · 종목상세 · 성과추적 · 레짐게이지 · 스캐너   │
│ 차트: lightweight-charts / ECharts                     │
└────────────────────────────────────────────────────────┘
```

### 일일 타임라인

```
[장전 ~08:30]        15:20 (특수=마감−10)        15:30           익일 08:30~09:10+
   │ pykrx FINAL        │ KIS 스냅샷 (~14s)         │ 종가단일가      │ 확정종가 채점
   │ prefetch·캐시      │ 파이프라인 ①~⑦           │ (익일 확정값)   │ + 오전 VWAP(09–10)
   │ + 헬스체크         │ 보드 발행 + top3 알림     │                 │ + DART 오버나잇 재스캔
   ▼ (실패→fail-closed) ▼ (커버리지<70%→미발행)     ▼                 ▼ 적중률/종목별 결과 갱신
  FINAL 확정          PROVISIONAL 확정                              POST-CLOSE 확정
```

데이터 신선도 4분류(임계경로 분리):

| 분류 | 항목 | 조달 |
|---|---|---|
| FINAL | 전일 EOD OHLCV·H_ref·20일평균·ATR20·D-1 외인/기관·지수이력·관리/경고지정 | 장전 prefetch·캐시 |
| PROVISIONAL | 당일 현재가·누적거래량·지수레벨·과열·거래정지 | KIS 인트라데이 REST |
| MODELED | RVOL 15:20-시점 평균 분모 | 스냅샷 축적 or 볼륨프로파일 |
| POST-CLOSE(함정) | 당일 공식 수급, post-15:30 공시 | 자동 점수화 금지·익일 재스캔 |

---

## 1. 증권 API를 어떻게 쓰는가 (3구간 호출)

### 인덱스 코드 매핑 (충돌 주의 — 중앙 매핑 + 동일성 단위테스트)

| 시장 | pykrx | KIS |
|---|---|---|
| KOSPI | `1001` | `0001` |
| KOSDAQ | `2001` | `1001` |

### 구간 1 — 장전 prefetch (pykrx, FINAL, 임계경로 밖)

| # | 호출 | TR/함수 | 산출 |
|---|---|---|---|
| 1 | 유니버스 | `get_market_ticker_list(D-1)` | point-in-time 티커 목록 |
| 2 | 일봉 이력 | `get_market_ohlcv(from,to,ticker)` | H_ref(252/60 롤링최대), ATR20, 20일 평균거래대금 |
| 3 | D-1 수급 | `get_market_net_purchases_of_equities(...)` | **시장별 1회 = 총 2회**(외인/기관 컬럼 동시), per-ticker 반복 금지, value 컬럼 |
| 4 | 지수 이력 | `get_index_ohlcv` ×2 (1001/2001) | 5일선 4/5항 |
| 5 | 위생 정적 | 관리/경고/위험 지정 목록 | 정적 필터 캐시 |

장전 헬스체크: 최근 거래일·행수 검증, 실패 시 런 차단(fail-closed).

### 구간 2 — 15:20 스냅샷 (KIS 순차 REST, PROVISIONAL)

```
순차 폴링 예산: ~265콜 @ 20req/s ≈ 14초  (15:20–15:30 창 내)
─────────────────────────────────────────────────────────
[a] 거래대금 랭킹  FHPST01710000  ×2  (KOSPI top-30, KOSDAQ top-30)
[b] 지수 현재가    FHPUP02100000  ×2  (0001 KOSPI, 1001 KOSDAQ)
[c] 종목 시세      FHKST01010100  ×~260 (정적위생 통과분만)
        └─ 현재가 · 15:20 누적거래량 · 등락률(과열) · 거래정지 플래그
─────────────────────────────────────────────────────────
후보풀 = pykrx D-1 거래대금 상위 200(캐시) ∪ KIS 라이브 top-30×2
정적위생 통과분에만 [c] 발사 → 레이트버짓 보호
```

> 웹소켓은 41종목 제약으로 스냅샷 부적합 → 순차 REST. WS는 top-3 실시간 새로고침 옵션만.

### 구간 3 — 익일 채점 (pykrx + KIS + DART)

| # | 호출 | 산출 |
|---|---|---|
| 1 | pykrx `get_market_ohlcv` 확정 | 매수가 = 15:30 확정 종가로 대체 |
| 2 | KIS 분봉 → 09:00–10:00 VWAP | 청산가(채점 기준) |
| 3 | DART `list.json` 재스캔 | 오버나잇 공시 플래그(추천 불변, 로그만) |

### 실패 / 저하 모드

| 장애 | 동작 |
|---|---|
| KIS 전면 불가 | 보드 미발행 + "데이터 미수신" (EOD 프록시 금지) |
| KIS 부분 실패 | 반환분만 채점 + 커버리지% , **<70% 미발행** |
| DART 불가 / corp_code 미매핑 | **veto fail-CLOSED**(확인 불가 → 제외) |
| pykrx D-1 불가 | 런 차단 + 알림 |
| KIS 토큰 만료(~24h) | 만료기반 갱신 + 재발급 throttle 캐시 |
| pykrx brittle/stale | 프리오픈 헬스체크·재시도, stale 시 fail-closed |
| VI/거래정지 엔드포인트 부재 | 과열가드 폴백 = 상한가/등락률≥+20% |

---

## 2. 추천 종목 판단을 어떻게 하는가

### 파이프라인 (15:20, ①~⑦)

```
① 후보풀     pykrx D-1 거래대금 top200 ∪ KIS 라이브 top30×2
② 정적위생   우선주/ETF/ETN/SPAC 제외 · 20일평균거래대금≥10억 · 관리/경고/위험 제외
                                          │ (라이브 조회 전 → 레이트버짓 보호)
③ 라이브조회 통과분 ~260만 KIS 현재가/누적거래량 + 지수/과열/정지
④ 동적위생   과열(상한가·등락률≥+20%·VI) · 15:20 거래정지 제외
─────────────── 게이트 & 신호 ───────────────
   시황게이트  regime_mult ∈ {0, 0.5, 1.0}  (종목 소속시장 레짐)
   신호        s_신 · rvol_confirm · supply_tilt · veto
⑤ 점수       core = s_신 × rvol_confirm × supply_tilt
              final = core × regime_mult × veto
⑥ 랭킹       final>0 만, 내림차순 top30, tie-break=D-1 거래대금
              가격규칙(매수가/청산 CTA/목·손 freeze)
⑦ 저장+알림   SQLite + JSON 스냅샷, top3 푸시
```

> 실효 3축: ① 돌파강도(신) ② 시황 레짐 ③ 수급. 거(RVOL)는 **돌파의 확인 배수(곱)** — 가산 아님(신–거 중복 차단). 접·갈·조는 **시각만**, 가중합 미포함.

### 신호 계산 공식

**시황 (4상태 MECE, HARD 게이트)** — A=(지수≥5MA), B=(5MA 기울기>0)

| A | B | regime_mult | 의미 |
|---|---|---|---|
| T | T | 1.0 | 상승 5MA 위 |
| T | F | 0.5 | 5MA 위·꺾임(약화) |
| F | T | 0.5 | 상승 5MA 아래(눌림) |
| F | F | 0.0 | 하락추세 → 중단 |

**신 (52주 신고가 + 돌파 마그니튜드)** — 룩어헤드 금지(H_ref=전일까지 확정 고가)
```
near_X  = P_now / max(High[t-X..t-1])              # X∈{252,60}
term(n) = clip((n−0.90)/0.10, 0,1) + 0.3·clip((n−1.00)/0.05, 0,1)  # 돌파 캡 0.3 가산
s_신    = 0.7·term(near_252) + 0.3·term(near_60)
        (이력 120~251일: s_신 = term(near_60), 라벨 "가용구간 고가"; <120일 제외)
과열가드: 당일 등락률≥+20% or 상한가/VI → buy emit 금지
```

**거 (RVOL 확인 배수, MODELED 분모)**
```
RVOL         = 당일 15:20 누적거래량 / MODELED 15:20-시점 평균
s_거         = clip(log2(RVOL)/log2(3), 0, 1)
rvol_confirm = clip(0.6 + 0.4·s_거, 0.6, 1.0)
```

**수급 (D-1 확정, 양방향)**
```
z           = clip((외인+기관 D-1 순매수액) / 20일 평균거래대금, -1, 1)
supply_tilt = clip(1.0 + 0.2·z, 0.8, 1.2)
```

**재 (희석 veto)** — 화이트리스트: 유상증자결정/CB/BW/EB → `veto=0`. 무상증자·주식배당 제외(false-veto 금지). corp_code↔티커 미매핑 → fail-closed(`veto=0`). 윈도우 T-1 15:20 ~ T 15:20.

### 워크드 예시 (KOSDAQ 종목 A)

```
입력: P_now=24,500 | max High[252]=24,000 | max High[60]=23,500
      RVOL=2.5 | 외인+기관 D-1=+80억 | 20일평균거래대금=500억
      KOSDAQ: 지수≥5MA(T), 5MA기울기>0(T) | 희석공시 없음
─────────────────────────────────────────────────────────
near_252=1.0208 → term=clip(1.208)=1.0 + 0.3·clip(0.416)=0.125  → 1.125
near_60 =1.0426 → term=clip(1.426)=1.0 + 0.3·clip(0.852)=0.256  → 1.256
s_신          = 0.7·1.125 + 0.3·1.256                          = 1.164
s_거          = clip(log2(2.5)/log2(3))=clip(0.834)            = 0.834
rvol_confirm  = clip(0.6+0.4·0.834)                            = 0.934
z=clip(80/500)=0.16 → supply_tilt = 1.0+0.2·0.16              = 1.032
─────────────────────────────────────────────────────────
core  = 1.164 × 0.934 × 1.032                                 = 1.122  → 등급 S(≥0.8)
regime_mult=1.0, veto=1
final = 1.122 × 1.0 × 1.0                                     = 1.122  → 상위 랭크
```
> 등급(S/A/B/C)은 `core`(레짐 독립) 기준 컷오프: S≥0.8 / A≥0.6 / B≥0.4 / C>0. 레짐은 별도 게이지.

### 가격 규칙 (행마다 결정론)

| 항목 | 값 |
|---|---|
| 현재가 | 15:20 잠정 스냅샷 (워터마크) |
| 매수가 | 15:30 종가단일가 (15:20 잠정표시 → 익일 확정 대체, 둘 다 보관) |
| 청산(주 CTA·채점) | 익일 오전 VWAP(09:00–10:00) 매도 |
| 손절(참고) | `max(매수가 − 1.0·ATR20, 매수가·0.97)` |
| 목표(참고) | `직전 전고점>매수가 ? min(매수가+1.2·ATR20, 직전전고점) : 매수가+1.2·ATR20` |

성공 정의: `vwap_0900_1000[t+1] / close[t] − 1 > 0`. VWAP 결측/잠김 → N/A, 분모 제외.

---

## 3. UI에 무엇을 보여주는가

### 화면 A — 추천 보드 (메인)

```
┌────────────────────────────────────────────────────────────────────┐
│ 종가베팅 추천   2026-06-30   [시황 게이지: KOSPI ●1.0  KOSDAQ ●1.0]   │
│ 집계 적중률 58% (n=42)        정렬[등급▼] 필터[시장][수급배지]        │
├──┬────────┬───────┬───────┬──────────────┬─────┬──────────┬───────┤
│★ │종목/코드│현재가 │매수가 │청산=오전VWAP │등급 │신호배지   │미니차트│
│  │        │(잠정) │(잠정→확정)│  ★주 CTA   │S/A │          │       │
├──┼────────┼───────┼───────┼──────────────┼─────┼──────────┼───────┤
│★ │A 000660│24,500 │24,500*│ 매도 09–10   │ S  │신고가 RVOL│ ╱╲╱   │
│  │        │       │       │ 목3% 손-3%(참)│    │수급+ 시황●│       │
│  │B 005930│71,200 │71,200*│ 매도 09–10   │ A  │신고가 베이스│ ╱─╱  │
└──┴────────┴───────┴───────┴──────────────┴─────┴──────────┴───────┘
 * 잠정 종가 워터마크   목/손은 "보유 시" 종속 표기   상단 top3~5 강조+푸시
 빈 보드: regime 0.0 → "오늘은 시황 레짐상 추천 없음" 배너 / 0.5 → "반-리스크(0.5x)" 캡션
```

### 화면 B — 종목 상세

```
┌────────────────────────────────────────────────────┐
│ A 000660  현재가 24,500 [잠정]   등급 S  final 1.12 │
├────────────────────────────────────────────────────┤
│  일봉차트 ── 52주 고가선 ─ 전고점 ─ [베이스 박스]   │
│  ╱╲    ╱╲╱▔▔(돌파)                                  │
│ ─────────────────────────  [잠정 워터마크]          │
├──────────────── 신호 기여도 ───────────────────────┤
│ s_신 1.16 | rvol_confirm 0.93 | supply_tilt 1.03    │
│ regime 1.0 | veto 1 | core 1.12                     │
└────────────────────────────────────────────────────┘
```

### 화면 C — 성과 추적 (종목별 결과 + 집계)

```
┌─ 집계 ─────────────────────────────────────────────┐
│ 적중률 58% | 평균 오전수익률 +0.4% | 누적곡선 ╱╲╱   │
│ 등급별 S 64% A 55% | 레짐별 1.0:60% 0.5:48%          │
├─ 어제 픽 (확정 채점) ──────────────────────────────┤
│종목  등급 매수가(확정) 오전VWAP 수익률 결과 DART재스캔│
│A     S   24,480       24,610   +0.53% ✅성공  -      │
│C     B   8,120        8,090    -0.37% ❌실패  ⚠공시   │
│D     A   15,000       (잠김)    —      N/A    -      │
└────────────────────────────────────────────────────┘
 콜드스타트: 누적 픽<30 → "데이터 누적 중" 회색 캡션
```

### 화면 D/E — 레짐 게이지 · 후보 풀 스캐너 (RISK_OFF 시 전면 유지)

### 컴포넌트 ↔ 엔드포인트 매핑

| 화면 | 컴포넌트 | 엔드포인트 |
|---|---|---|
| A 추천보드 | `RecTable`, `RegimeGauge`, `MiniChart` | `GET /recommendations/{date}` |
| B 종목상세 | `StockDetail`, `SignalContribution` | `GET /stock/{code}` |
| C 성과추적 | `PerfTable`, `PerfAggregate` | `GET /performance` |
| D 레짐게이지 | `RegimeGauge` | `/recommendations`에 포함 |
| E 스캐너 | `Scanner` | `GET /universe` |
| (공통) | `HealthBadge` | `GET /health` |

---

## 4. 백엔드 모듈 / 저장소 구조

### 모듈 트리

```
backend/
  app/
    main.py                       FastAPI 진입·라우터 등록
    api/
      recommendations.py          GET /recommendations/{date}
      stock.py                    GET /stock/{code}
      performance.py              GET /performance
      backtest.py                 GET /backtest
      universe.py                 GET /universe
      health.py                   GET /health
    engine/
      pipeline.py                 15:20 오케스트레이션 ①~⑦
      signals/
        regime.py                 시황 4상태 게이트
        breakout.py               s_신 (near + 돌파 마그니튜드)
        rvol.py                   거 rvol_confirm (MODELED 분모)
        supply.py                 수급 supply_tilt (D-1)
        veto.py                   DART 희석 veto
        hygiene.py                정적/동적 위생필터
      scoring.py                  core / final
      grade.py                    S/A/B/C 컷오프 (core 기준)
      pricing.py                  매수가·청산·목표·손절 freeze
    data/
      broker_adapter.py           BrokerDataAdapter 추상 인터페이스
      kis_client.py               KIS TR 래퍼(FHPST01710000/FHKST01010100/FHPUP02100000)
      pykrx_client.py             EOD·D-1수급·지수이력
      dart_client.py              공시 list.json·corp_code
      mapping.py                  중앙 인덱스/티커 매핑(코드충돌 흡수)
    backtest/
      engine.py                   순수 pandas 백테스트 CLI
      reconstruct.py              풀 재구성·15:20-등가 스냅샷
      ic.py                       walk-forward rank-IC·직교화
    scheduler/
      premarket.py                장전 FINAL prefetch + 헬스체크
      daily_run.py                15:20 런(특수세션=마감−10)
      scoring_job.py              익일 확정 채점 + DART 재스캔
      calendar.py                 KRX 거래 캘린더·특수세션
    store/
      db.py                       SQLite 세션
      models.py                   ORM/스키마
      snapshots.py                state/recommendations/YYYY-MM-DD.json
  state/
    recommendations/YYYY-MM-DD.json
    cache/  (FINAL prefetch)
  tests/                          단위·어댑터 목·실패모드
frontend/
  src/
    pages/ Board.tsx StockDetail.tsx Performance.tsx
    components/ RecTable.tsx RegimeGauge.tsx MiniChart.tsx Scanner.tsx
                SignalContribution.tsx PerfTable.tsx HealthBadge.tsx
    api/client.ts
```

### SQLite 스키마

```sql
-- 일일 추천 (불변 스냅샷)
recommendations(
  id PK, run_date, ticker, name, market,            -- KOSPI/KOSDAQ
  rank, price_provisional, buy_price_provisional, buy_price_final,
  s_shin, s_geo, rvol_confirm, supply_tilt,
  regime_mult, veto, core, final, grade,            -- grade=core 기준
  near_252, near_60, rvol, target_price, stop_price,
  provisional_flag, created_at,
  UNIQUE(run_date, ticker))

-- 익일 채점
performance(
  rec_id FK→recommendations.id, eval_date,
  buy_price_final, vwap_0900_1000, morning_return,
  outcome,                                          -- SUCCESS/FAIL/NA
  dart_overnight_flag, scored_at)

-- RVOL 분모 축적 (~20세션 후 활성)
volume_snapshots(
  ticker, snapshot_date, cum_volume_1520, cum_value_1520,
  PK(ticker, snapshot_date))

-- 정적 위생 캐시 (장전)
universe_cache(
  ticker, name, market, sec_type,                   -- 우선주/ETF/ETN/SPAC
  avg_value_20d, is_managed, is_warning, is_caution,
  listing_days, eligible, as_of)

-- 시황 레짐 스냅샷
regime_snapshots(
  run_date, market, index_level, ma5, ma5_prev,
  cond_a, cond_b, regime_mult, PK(run_date, market))

-- DART 매핑
corp_code_map(corp_code PK, ticker, name, updated_at)

-- 런 감사 / 실패모드
runs(
  run_date PK, started_at, finished_at, status,     -- OK/UNPUBLISHED/BLOCKED
  kis_coverage_pct, board_published, session_type,  -- 정규/특수
  reason)
```

---

## 5. 배포 · 운영

### 운영 타임라인 시퀀스

```
참여자: Calendar │ Premarket │ Scheduler(15:20) │ KIS/pykrx/DART │ Store │ Notify │ ScoringJob
─────────────────────────────────────────────────────────────────────────────
Calendar  → 거래일?·마감시각 도출 (휴장/주말/특수세션 → 마감−10분)
Premarket → pykrx FINAL prefetch + 헬스체크 ──(실패)──▶ 런 차단 + 알림
Scheduler → 15:20 트리거
   │  ① 후보풀  ② 정적위생  ③ KIS 라이브 ~14s  ④ 동적위생
   │  ⑤ 신호·게이트  ⑥ core/final·top30·가격규칙
   │──(커버리지<70%)──▶ 미발행 + 사유 로그
   │  ⑦ Store.write(SQLite+JSON) → Notify.push(top3)
ScoringJob(익일) → 확정종가·오전VWAP 채점(N/A) + DART 오버나잇 재스캔
                 → 적중률·종목별 결과 갱신
```

### 토폴로지 2안

```
[안 A — 로컬 PC 상시]                    [안 B — 별도 호스트]
┌─────────────────────┐                  ┌─────────────────────┐
│ Windows 작업스케줄러 │                  │ VPS / 클라우드 VM    │
│  └ premarket/15:20/  │                  │  systemd timer       │
│    scoring 잡        │                  │   ├ premarket.timer  │
│ FastAPI(localhost)   │                  │   ├ daily-run.timer  │
│ React 정적빌드       │                  │   └ scoring.timer    │
│ SQLite 로컬파일      │                  │ FastAPI + Nginx      │
│ 알림: 데스크톱/푸시  │                  │ SQLite/볼륨 백업     │
└─────────────────────┘                  │ 알림: 푸시/웹훅      │
 장점: 무비용·간단                        └─────────────────────┘
 단점: PC 상시가동 의존                    장점: 무인·안정 / 단점: 비용·운영
```

> 15:20 정시성이 핵심(10분 결정창). PC 절전/네트워크 끊김 리스크가 크면 안 B 권장.

### 스케줄러 / 거래 캘린더

| 항목 | 정책 |
|---|---|
| 거래일 판정 | KRX 거래 캘린더(휴장·주말 제외) |
| 정규 세션 | 15:30 마감 → 스냅샷 15:20 |
| 특수 세션 | 캘린더에서 마감시각 도출 → 스냅샷=마감−10분, 매수가=해당 세션 종가단일가(조기폐장/반일) |
| 수능 지연개장 | 마감 15:30 유지 |
| 비표준 세션 데이터 불신 | 추천 보류 + 사유 로그 |
| 채점 매핑 | t→t+1 = 다음 거래일 |
| KIS 토큰 | 만료(~24h) 기반 갱신 + 재발급 throttle 캐시 |

### 발행 게이트 (보드 '완료' 정의)

- 15:20–15:30 창 내 산출(레이턴시 버짓 준수)
- 최소 커버리지 바닥(≥70%) 충족 시에만 발행
- 자동 룩어헤드 / 풀-재현 가드 테스트 그린(엣지 입증 전에도 필수)