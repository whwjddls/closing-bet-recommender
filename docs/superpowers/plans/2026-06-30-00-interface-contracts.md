# 서브시스템 간 인터페이스 계약 (Interface Contracts) — 단일 진실원천

> **우선순위 규칙:** 이 문서는 5개 구현 플랜(01~05)의 **경계(seam) 계약에 대한 단일 진실원천**이다.
> 개별 플랜의 Task 본문과 이 문서가 **충돌하면 이 문서가 우선**한다. 각 플랜은 자기 내부 TDD는 그대로 따르되,
> 아래에 정의된 시그니처/스키마/모델명을 **그대로** 사용해야 한다.
>
> 배경: 5개 플랜을 병렬 작성하여 내부 TDD 품질은 우수하나 경계 계약이 어긋났다(저장소 기술, run_pipeline 시그니처,
> 데이터레이어 함수 누락, BacktestResult 부재, API↔프론트 스키마). 이 문서가 그 균열을 닫는다.

적용 대상 결함: 리뷰 B1·B2·M1·M2·M3·M4 + 관련 minor 다수. (B3 rvol 상수 오류는 플랜 02 본문에서 직접 교정됨.)

---

## §1. 저장소 — SQLAlchemy 2.0 ORM (B1 해소)

**결정:** store 레이어는 **SQLAlchemy 2.0 ORM**으로 단일화한다. (01의 raw sqlite3+dataclass 안 폐기 — 04/05가 ORM을 전제하므로 01을 승격.)

`backend/pyproject.toml` dependencies에 추가: `sqlalchemy>=2.0`, `pydantic>=2`, `numpy`, `plyer`. (설치 스텝: 01 Task1에 `cd backend && pip install -e ".[dev]"` 포함.)

### `app/store/db.py`
```python
from collections.abc import Iterator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ENGINE_URL = "sqlite:///state/closing_bet.db"
engine = create_engine(ENGINE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)

def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db() -> None:
    from app.store.models import Base
    Base.metadata.create_all(engine)
```

### `app/store/models.py` — `Base(DeclarativeBase)` + ORM 모델 (컬럼명은 아키텍처 §4 그대로)
- `Recommendation` (table `recommendations`): id PK, run_date(Date), ticker, name, market, rank, price_provisional, buy_price_provisional, buy_price_final(nullable), s_shin, s_geo, rvol_confirm, supply_tilt, regime_mult, veto(bool/int), core, final, grade, near_252, near_60, rvol, target_price, stop_price, **spark(JSON list[float])**, **base_flag(bool)**, provisional_flag(bool), created_at. `UNIQUE(run_date, ticker)`.
- `Performance` (table `performance`): id PK, rec_id FK→recommendations.id, eval_date(Date), buy_price_final, vwap_0900_1000(nullable), morning_return(nullable), outcome(str: `SUCCESS`/`FAIL`/`NA`), dart_overnight_flag(bool), scored_at.
- `VolumeSnapshot` (table `volume_snapshots`): ticker, snapshot_date(Date), cum_volume_1520, cum_value_1520. `PK(ticker, snapshot_date)`.
- `UniverseCache` (table `universe_cache`): ticker, as_of(Date), name, market, sec_type, avg_value_20d, is_managed, is_warning, is_caution, listing_days, eligible. `PK(ticker, as_of)`.
- `RegimeSnapshot` (table `regime_snapshots`): run_date(Date), market, index_level, ma5, ma5_prev, cond_a(bool), cond_b(bool), regime_mult. `PK(run_date, market)`.
- `CorpCodeMap` (table `corp_code_map`): corp_code PK, ticker, name, updated_at.
- `Run` (table `runs`): run_date(Date) PK, started_at, finished_at, status(str: `OK`/`UNPUBLISHED`/`BLOCKED`), kis_coverage_pct, board_published(bool), session_type(str), reason.

### `app/store/snapshots.py`
```python
def write_snapshot(run_date: "datetime.date", payload: dict) -> str:
    """state/recommendations/YYYY-MM-DD.json 저장, 경로 반환. (2-인자 — 04 시그니처)"""
```

04/05 및 모든 conftest는 `from app.store.models import Base`, `from app.store.db import get_db, SessionLocal, engine, init_db` 를 사용한다. 01의 round-trip 테스트도 이 ORM 계약으로 작성.

---

## §2. 데이터 레이어 공개 표면 (M1 해소)

**규칙:** 04 스케줄러/API는 아래 **모듈 레벨 함수**를 정본 인터페이스로 호출한다. `BrokerDataAdapter`(01 ABC)는 이 함수들을 감싸는 어댑터이며, 테스트는 모듈 함수를 목한다.

### `app/data/pykrx_client.py`
```python
def get_universe(d: date) -> list[str]: ...
def get_ohlcv(ticker: str, frm: date, to: date) -> "pd.DataFrame": ...
def get_net_purchases(market: str, frm: date, to: date) -> "pd.DataFrame":  # 외인+기관 value, 시장별 1회(총2회)
def get_index_ohlcv(index_code: str, frm: date, to: date) -> "pd.DataFrame": ...
def prefetch_final(run_date: date) -> "PrefetchBundle":   # H_ref(252/60)·ATR20·20일평균거래대금·D-1수급·지수5MA·정적위생
def fetch_confirmed_close(ticker: str, d: date) -> float: # 익일 채점용 15:30 확정 종가
def health_check() -> "HealthResult":                     # 무인자 모듈함수
```
```python
@dataclass
class HealthResult:
    ok: bool
    latest_trading_day: date
    rows: int
    detail: str
```
`health_check()`는 지수 OHLCV **그리고 D-1 외인/기관 수급·거래대금** 조회 성공을 함께 검증한다(수급 결손 시 `ok=False`). (M-spec: pykrx D-1 불가 → 런 차단.)

### `app/data/kis_client.py`
```python
@dataclass
class Quote:
    ticker: str; price: float; cum_volume: int; change_pct: float
    is_halted: bool; is_limit_up: bool; is_vi: bool      # 상한가·VI 플래그 포함(폴백 아님)
def get_quote(ticker: str) -> Quote: ...                 # TR FHKST01010100
def get_value_ranking(market: str, top: int = 30) -> list[str]:  # TR FHPST01710000
def get_index_level(index_code: str) -> float: ...       # TR FHPUP02100000 (KIS 코드 0001/1001)
def fetch_morning_vwap(ticker: str, d: date) -> float | None:    # 익일 09:00–10:00 VWAP(분봉), 결측 None
```
VI 발동종목 전용 엔드포인트가 없으면 `is_vi`는 best-effort(상한가/등락률≥+20%로 과열 폴백) — 그래도 필드는 항상 존재.

### `app/data/dart_client.py`
```python
WHITELIST = ("유상증자결정","전환사채권발행결정","신주인수권부사채권발행결정","교환사채권발행결정")
def dilution_veto(ticker: str, snapshot_at: datetime) -> int:
    """T-1 15:20 ~ snapshot_at(=T 15:20) 확정 공시만. 보고서명 substring 매칭(정정 변형 포착),
       무상증자/주식배당 제외. corp_code 미매핑 → 0(fail-closed). post-15:20 당일공시는 라이브 veto 제외."""
def overnight_scan(ticker: str, since: datetime, until: datetime) -> bool:  # 익일 재스캔(성과 로그용)
def refresh_corp_codes() -> int:                          # corpCode.xml 다운로드·upsert
```
**룩어헤드 정정(minor):** 라이브 veto 윈도우는 접수시각(분, 상세계층)으로 ≤15:20 필터. 시각 불가 시 당일(T) 공시는 라이브 veto에서 **제외**하고 익일 `overnight_scan`으로만 플래그.

---

## §3. 엔진 ↔ 오케스트레이터 (B2·M4 해소)

### 순수 엔진 (플랜 02, 시그니처 유지)
```python
def run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg_by_ticker,
                 veto_by_ticker, max_emit=30) -> PipelineResult: ...
@dataclass
class PipelineResult:
    published: bool; reason: str | None
    rows: list["EngineRow"]; coverage_pct: float          # 0.0~1.0 (비율)
```
02는 순수 함수 유지(데이터 수집/레짐 산출/영속화 안 함). 신호 export 시그니처(03이 참조):
`s_shin(p_now, high_60, high_252, listing_days)`, `rvol_confirm(rvol)`, `supply_z(net, avg)`+`supply_tilt(z)`, `compute_regime(index_level, prev5_closes)`, `core_score(s_shin, rvol_confirm, supply_tilt)`, `final_score(core, regime_mult, veto)`, `grade_of(core)`.

### 오케스트레이터 (신규 모듈 `app/engine/orchestrator.py` — **플랜 04 소유**)
```python
def orchestrate_run(run_date: date, snapshot_at: datetime, *, store=SessionLocal) -> "RunResult": ...
```
책임 (TDD로 고정):
1. 후보풀 = `pykrx_client` D-1 거래대금 top200 **∪** `kis_client.get_value_ranking` KOSPI/KOSDAQ top30×2 (스펙 §3.3 ①).
2. 정적 위생(universe_cache) → 통과분만 `get_quote` 라이브 조회 → 동적 위생(과열/거래정지).
3. **MODELED RVOL 생산자(M4):** 매 런 당일 `cum_volume_1520`을 `volume_snapshots`에 upsert → trailing **≥20세션** 평균으로 `modeled_avg_by_ticker` 산출(20세션 미만 → None → rvol_confirm=1.0 중립).
4. 시장별 `compute_regime` 산출 → `RegimeSnapshot` 영속화 → `regime_by_market` 주입(종목 소속시장 레짐).
5. `dilution_veto` → `veto_by_ticker`.
6. `run_pipeline(...)` 호출 → `EngineRow` → **`RecRow`** 변환, `coverage_pct×100` → `kis_coverage_pct`.
```python
@dataclass
class RegimeInfo: market: str; index_level: float; ma5: float; regime_mult: float; cond_a: bool; cond_b: bool
@dataclass
class RecRow:  # API 직렬화 직전형 (recommendations 컬럼 + spark/base_flag)
    rank:int; ticker:str; name:str; market:str
    price_provisional:float; buy_price_provisional:float; buy_price_final:float|None
    target_price:float; stop_price:float
    s_shin:float; s_geo:float; rvol_confirm:float; supply_tilt:float
    regime_mult:float; veto:int; core:float; final:float; grade:str
    near_252:float; near_60:float; rvol:float
    spark:list[float]; base_flag:bool; provisional_flag:bool
@dataclass
class RunResult:
    run_date:date; session_type:str; data_available:bool; kis_coverage_pct:float  # 0~100
    recommendations:list[RecRow]; regimes:dict[str,RegimeInfo]; reason:str|None
```
04의 `daily_run`과 `/recommendations` API는 `orchestrate_run`/저장된 `RunResult`를 소비한다.

---

## §4. 백테스트 공개 API (M2 해소)

### `app/backtest/engine.py` — 공개 래퍼 추가 (플랜 03)
```python
def run_backtest(start: date, end: date) -> "BacktestResult":
    """내부: reconstruct(풀·15:20등가) → score(확정종가 진입·익일오전VWAP 채점) → summarize → ic.walk_forward_rank_ic/acceptance 묶음."""
@dataclass
class BacktestResult:
    start: date; end: date; n_picks: int
    rank_ic: float; t_stat: float; hit_rate: float; avg_return: float; note: str
```
04 `/backtest`는 `from app.backtest.engine import run_backtest`로 바인딩. 03의 "의존 인터페이스" 블록은 §3의 02 실제 export 시그니처로 정정.

---

## §5. API 응답 스키마 (M3 해소) — 04↔05 정본 (pydantic v2)

> 05 `client.ts` 타입은 아래와 **정확히** 일치. 04 라우터는 아래로 직렬화하고 **응답 스키마 테스트**를 박는다.

```python
class Candle(BaseModel): date:str; open:float; high:float; low:float; close:float; volume:int
class BaseBox(BaseModel): start:str; end:str; low:float; high:float

class RecommendationRow(BaseModel):
    rank:int; ticker:str; name:str; market:str
    price_provisional:float; buy_price_provisional:float; buy_price_final:float|None
    exit_label:str = "익일 오전 VWAP(09:00–10:00)"
    target_price:float; stop_price:float
    score:float                      # = final
    grade:str                        # S/A/B/C (core 기준)
    badges:list[str]                 # 신고가/RVOL/수급/시황/베이스
    near_252:float; near_60:float; rvol:float
    s_shin:float; rvol_confirm:float; supply_tilt:float; regime_mult:float; veto:int
    spark:list[float]; base_flag:bool; provisional_flag:bool

class StockDetailResponse(BaseModel):
    ticker:str; name:str; price_provisional:float; grade:str; final:float
    candles:list[Candle]; high_52w:float; prior_high:float; base_box:BaseBox|None
    contributions:dict   # {s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}

class PickResult(BaseModel):
    ticker:str; name:str; grade:str
    buy_price_final:float; vwap_0900_1000:float|None; morning_return:float|None
    outcome:str          # SUCCESS/FAIL/NA
    dart_overnight_flag:bool
class GradeBucket(BaseModel): grade:str; hit_rate:float; n:int
class RegimeBucket(BaseModel): regime:str; hit_rate:float; n:int
class CurvePoint(BaseModel): date:str; cum:float
class PerformanceAggregate(BaseModel):
    sample_size:int; hit_rate:float; avg_morning_return:float
    cumulative_curve:list[CurvePoint]
    by_grade:list[GradeBucket]; by_regime:list[RegimeBucket]
    cold_start:bool      # sample_size<30
class PerformanceResponse(BaseModel):
    eval_date:str; picks:list[PickResult]; aggregate:PerformanceAggregate

class HealthResponse(BaseModel):
    status:str           # 'OK'|'DEGRADED'|'DOWN'  (대문자)
    reason:str           # 사유(필드명 reason, detail 아님)
    kis_coverage_pct:float; board_published:bool; last_run_date:str|None
```
`/recommendations/{date}` → `{run_date, session_type, data_available, kis_coverage_pct, regimes:dict[str,RegimeInfo], recommendations:list[RecommendationRow]}`. `/universe` → 스캐너 행. 빈/저레짐: `data_available=true, recommendations=[]` + 사유.

---

## §6. 공통 정정 (실행 중 적용)

- **pyproject 의존성**: §1 참조(sqlalchemy·pydantic·numpy·plyer). 각 도입 플랜 첫 Task에서 추가, 01 Task1에 설치 스텝.
- **커밋 트레일러**: 5개 플랜 **모두** `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>` 포함(03/04 누락분 보강).
- **기대 통과 개수**: 플랜의 "N passed" 수치는 **참고용** — 실제 `pytest`/`vitest` 출력의 RED→GREEN 전환을 게이트로 삼는다(수치 오기 다수, 기능 결함 아님).
- **혼합시장 레짐 테스트(02)**: KOSPI·KOSDAQ 종목 혼합 + `regime_by_market={'KOSPI':0.0,'KOSDAQ':1.0}`로 교차오염 없음 고정.
- **premarket 헬스체크(04)**: §2 `health_check()`가 D-1 수급 포함 → 결손 시 `BLOCKED` 테스트.
- **비표준 세션(04, 저우선)**: 데이터 불신 시 `UNPUBLISHED(reason='비표준 세션 데이터 불신')`.
- **corp_code 갱신(01/04, 저우선)**: `refresh_corp_codes` 잡을 premarket에 배선.
