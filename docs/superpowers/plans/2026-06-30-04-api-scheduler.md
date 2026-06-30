# 서브시스템 4 — API & 스케줄러 Implementation Plan

> ⚠️ **계약 우선:** [`00-interface-contracts.md`](2026-06-30-00-interface-contracts.md) §1·§3·§5. store는 01 ORM 소비. 엔진 소비는 **신규 `app/engine/orchestrator.py`의 `orchestrate_run`(§3, 본 플랜 소유)** 경유. MODELED RVOL 생산자(volume_snapshots upsert+trailing≥20 평균) 소유. API 응답 스키마는 §5 정본. premarket 헬스체크에 D-1 수급 포함.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** 추천 엔진(서브시스템 2)·데이터/스토어(서브시스템 1)·백테스트(서브시스템 3) 위에 FastAPI 6개 엔드포인트와 4개 Windows 작업스케줄러 잡(장전 prefetch·15:20 런·익일 채점·거래 캘린더)을 얹어, fail-closed/커버리지 게이트/룩어헤드 가드를 테스트로 박은 발행·채점 파이프라인을 완성한다.

**Architecture:** FastAPI `create_app()` 팩토리가 6개 `APIRouter`를 등록하고 `store/db.py`의 `get_db` 의존성으로 SQLite를 읽는다(읽기 전용 조회). 스케줄러 3잡은 `calendar.py`의 `TradingCalendar`로 거래일·마감시각(특수세션=마감−10)을 판정하고, 엔진/데이터/스토어 콜라보레이터를 **주입**받아 SQLite(`runs`/`recommendations`/`regime_snapshots`/`performance`)와 JSON 스냅샷에 쓴다. 모든 외부 API(KIS/pykrx/DART)는 주입 경계 뒤에 두어 테스트는 목으로만 돌고 네트워크 호출이 없다.

**Tech Stack:** Python 3.14 · FastAPI · pydantic v2 · SQLAlchemy 2.0 ORM · SQLite · pytest · Windows 작업스케줄러(PowerShell `Register-ScheduledTask`).

---

## File Structure

```
backend/
  app/
    main.py                      [생성] FastAPI 앱 팩토리 + 라우터 등록 + CORS
    api/
      __init__.py                [생성]
      schemas.py                 [생성] 전 엔드포인트 pydantic 응답 모델(태스크별 증분)
      health.py                  [생성] GET /health
      recommendations.py         [생성] GET /recommendations/{run_date}
      stock.py                   [생성] GET /stock/{code}
      performance.py             [생성] GET /performance
      universe.py                [생성] GET /universe
      backtest.py                [생성] GET /backtest
    scheduler/
      __init__.py                [생성]
      calendar.py                [생성] KRX 거래 캘린더·휴장·조기폐장·수능지연
      premarket.py               [생성] 장전 FINAL prefetch + 헬스체크 fail-closed
      daily_run.py               [생성] 15:20 파이프라인 실행·커버리지 게이트·top3 알림
      scoring_job.py             [생성] 익일 09~10 채점(N/A) + DART 오버나잇 재스캔
  scripts/
    register_tasks.ps1           [생성] Windows 작업스케줄러 3잡 등록
    README_scheduler.md          [생성] 등록·운영 문서
  tests/
    api/{conftest.py,test_health.py,test_recommendations.py,test_stock.py,
         test_performance.py,test_universe.py,test_backtest.py}   [생성]
    scheduler/{test_calendar.py,test_premarket.py,test_daily_run.py,
               test_scoring_job.py}                               [생성]
    acceptance/test_mvp_gates.py                                  [생성]
```

> 명령은 모두 `backend/` 디렉터리에서 실행한다(`app` 패키지 임포트 기준). git 명령만 리포 루트(`closing-bet-recommender/`)에서 실행한다.

---

## 의존 인터페이스 계약 (서브시스템 1·2·3에서 고정 — 본 플랜은 소비만)

아래 시그니처는 아키텍처 모듈 트리·SQLite 스키마·신호 공식에 고정된 것을 그대로 소비한다. 스케줄러는 이 콜라보레이터들을 **주입**받으므로(기본값은 지연 임포트로 바인딩) 테스트는 목으로만 동작한다.

```python
# ── 서브시스템 1 (data + store) ────────────────────────────────────────────
# app/store/db.py
Base                                  # SQLAlchemy DeclarativeBase (models에서 정의, db에서 재노출)
SessionLocal                          # sessionmaker[Session]
def get_db() -> Iterator[Session]     # FastAPI 의존성(Session yield)

# app/store/models.py  (컬럼명 = 아키텍처 §4 SQLite 스키마와 1:1)
class Recommendation(Base):  # run_date(Date), ticker, name, market, rank,
#   price_provisional, buy_price_provisional, buy_price_final,
#   s_shin, s_geo, rvol_confirm, supply_tilt, regime_mult, veto,
#   core, final, grade, near_252, near_60, rvol, target_price, stop_price,
#   provisional_flag(bool), created_at, id(PK), UNIQUE(run_date,ticker)
class Performance(Base):     # id, rec_id(FK), eval_date(Date), buy_price_final,
#   vwap_0900_1000, morning_return, outcome, dart_overnight_flag(bool), scored_at
class RegimeSnapshot(Base):  # run_date(Date), market, index_level, ma5, ma5_prev,
#   cond_a(bool), cond_b(bool), regime_mult ; PK(run_date, market)
class UniverseCache(Base):   # ticker(PK), name, market, sec_type, avg_value_20d,
#   is_managed, is_warning, is_caution, listing_days, eligible(bool), as_of(Date)
class Run(Base):             # run_date(Date,PK), started_at, finished_at,
#   status('OK'|'UNPUBLISHED'|'BLOCKED'), kis_coverage_pct,
#   board_published(bool), session_type('정규'|'특수'), reason

# app/store/snapshots.py
def write_snapshot(run_date: date, payload: dict) -> Path

# app/data/pykrx_client.py
def health_check() -> Any              # .ok(bool) .latest_trading_day(date) .rows(int) .detail(str)
def prefetch_final(run_date: date) -> None   # universe_cache/regime/cache 채움
def fetch_confirmed_close(ticker: str, d: date) -> float | None   # 확정 종가 close[t]
# app/data/kis_client.py
def fetch_morning_vwap(ticker: str, d: date) -> float | None      # 09:00–10:00 VWAP, 잠김/결측 None
# app/data/dart_client.py
def overnight_scan(ticker: str, since: datetime, until: datetime) -> bool

# ── 서브시스템 2 (engine) ──────────────────────────────────────────────────
# app/engine/pipeline.py
@dataclass class RegimeInfo:  market,index_level,ma5,ma5_prev,cond_a,cond_b,regime_mult
@dataclass class RecRow:      rank,ticker,name,market,price_provisional,
#   buy_price_provisional,s_shin,s_geo,rvol_confirm,supply_tilt,regime_mult,veto,
#   core,final,grade,near_252,near_60,rvol,target_price,stop_price,provisional_flag
@dataclass class PipelineResult:  run_date,session_type,data_available(bool),
#   kis_coverage_pct(float),recommendations(list[RecRow]),regimes(dict[str,RegimeInfo])
def run_pipeline(run_date: date, snapshot_at: datetime) -> PipelineResult

# ── 서브시스템 3 (backtest, /backtest 한정) ────────────────────────────────
# app/backtest/engine.py
@dataclass class BacktestResult: start,end,n_picks,rank_ic,t_stat,hit_rate,avg_return,note
def run_backtest(start: date, end: date) -> BacktestResult
```

---

## Task 1: 거래 캘린더 (`scheduler/calendar.py`)

**Files:** Create `backend/app/scheduler/__init__.py`, `backend/app/scheduler/calendar.py`; Test `backend/tests/scheduler/test_calendar.py`

거래일/마감시각/스냅샷시각/특수세션을 **순수 함수**로 계산한다. 휴일/조기폐장 표를 주입받아 네트워크 없이 결정론적으로 동작한다. 핵심 규칙: 정규=마감 15:30·스냅샷 15:20, 특수세션(조기폐장)=마감−10분, 수능 지연개장=마감 15:30 유지(특수 아님), 채점 매핑 t→t+1=다음 거래일.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/scheduler/test_calendar.py
from datetime import date, datetime, time
from app.scheduler.calendar import TradingCalendar, REGULAR_CLOSE, SNAPSHOT_OFFSET

# 2026-06-30(화) 정상, 2026-07-01(수) 휴장 가정, 2026-09-29(화) 조기폐장 14:00(반일),
# 2026-11-19(목) 수능일=지연개장이지만 마감 15:30 유지(특수 아님)
HOLIDAYS = {date(2026, 7, 1)}
EARLY_CLOSE = {date(2026, 9, 29): time(14, 0)}

def _cal():
    return TradingCalendar(holidays=HOLIDAYS, early_close=EARLY_CLOSE)

def test_weekend_and_holiday_are_not_trading_days():
    cal = _cal()
    assert cal.is_trading_day(date(2026, 6, 30)) is True
    assert cal.is_trading_day(date(2026, 7, 4)) is False    # 토요일
    assert cal.is_trading_day(date(2026, 7, 5)) is False    # 일요일
    assert cal.is_trading_day(date(2026, 7, 1)) is False    # 휴장

def test_regular_session_snapshot_is_1520_within_window():
    cal = _cal()
    d = date(2026, 6, 30)
    assert cal.close_time(d) == REGULAR_CLOSE == time(15, 30)
    snap = cal.snapshot_at(d)
    assert snap == datetime(2026, 6, 30, 15, 20)
    assert time(15, 20) <= snap.time() < time(15, 30)       # 15:20–15:30 창
    assert cal.session_type(d) == "정규"

def test_early_close_session_snapshot_is_close_minus_10():
    cal = _cal()
    d = date(2026, 9, 29)
    assert cal.close_time(d) == time(14, 0)
    assert cal.snapshot_at(d) == datetime(2026, 9, 29, 13, 50)   # 마감−10
    assert cal.session_type(d) == "특수"

def test_csat_day_keeps_1530_close_not_special():
    cal = _cal()  # 수능일은 early_close에 없음 → 정규 취급
    d = date(2026, 11, 19)
    assert cal.close_time(d) == time(15, 30)
    assert cal.snapshot_at(d) == datetime(2026, 11, 19, 15, 20)
    assert cal.session_type(d) == "정규"

def test_next_and_prev_trading_day_skip_holiday_and_weekend():
    cal = _cal()
    # 2026-06-30(화) → next = 07-02(목, 07-01 휴장 건너뜀)
    assert cal.next_trading_day(date(2026, 6, 30)) == date(2026, 7, 2)
    # 2026-07-02(목) → prev = 06-30(화)
    assert cal.prev_trading_day(date(2026, 7, 2)) == date(2026, 6, 30)
    assert SNAPSHOT_OFFSET == __import__("datetime").timedelta(minutes=10)
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/scheduler/test_calendar.py -q
# 기대: ModuleNotFoundError: No module named 'app.scheduler.calendar'  → 5 errors
```

- [ ] **Step 3: 최소 구현**

```python
# backend/app/scheduler/__init__.py
```
```python
# backend/app/scheduler/calendar.py
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

REGULAR_CLOSE: time = time(15, 30)        # 정규장 마감
SNAPSHOT_OFFSET: timedelta = timedelta(minutes=10)   # 스냅샷 = 마감−10분


@dataclass(frozen=True)
class TradingCalendar:
    """KRX 거래 캘린더. 휴일/조기폐장 표를 주입받아 결정론적으로 동작한다."""
    holidays: set[date] = field(default_factory=set)
    early_close: dict[date, time] = field(default_factory=dict)

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def close_time(self, d: date) -> time:
        # 조기폐장(특수)만 마감 단축. 수능 지연개장은 표에 없으므로 15:30 유지.
        return self.early_close.get(d, REGULAR_CLOSE)

    def snapshot_at(self, d: date) -> datetime:
        return datetime.combine(d, self.close_time(d)) - SNAPSHOT_OFFSET

    def session_type(self, d: date) -> str:
        return "특수" if d in self.early_close else "정규"

    def next_trading_day(self, d: date) -> date:
        nxt = d + timedelta(days=1)
        while not self.is_trading_day(nxt):
            nxt += timedelta(days=1)
        return nxt

    def prev_trading_day(self, d: date) -> date:
        prv = d - timedelta(days=1)
        while not self.is_trading_day(prv):
            prv -= timedelta(days=1)
        return prv


def load_default_calendar() -> "TradingCalendar":
    """운영용 기본 캘린더. 휴일/조기폐장 표는 운영 데이터(번들 JSON/pykrx)에서 주입.
    스케줄러는 테스트에서 명시적 캘린더를 주입하므로 여기서는 빈 표로 시작한다."""
    return TradingCalendar(holidays=set(), early_close={})
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/scheduler/test_calendar.py -q
# 기대: 5 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/scheduler/__init__.py backend/app/scheduler/calendar.py backend/tests/scheduler/test_calendar.py
git commit -m "feat(scheduler): KRX 거래 캘린더(휴장·조기폐장·수능지연·t→t+1)"
```

---

## Task 2: FastAPI 앱 팩토리 + `GET /health` (`main.py`, `api/health.py`, `api/schemas.py`)

> **[00 §5 정본]** `HealthResponse.status`는 **대문자** `'OK'|'DEGRADED'|'DOWN'`, 사유 필드명은 **`reason`**(detail 아님) + `kis_coverage_pct`/`board_published`/`last_run_date`. store는 01 SQLAlchemy ORM 소비.

**Files:** Create `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/api/schemas.py`, `backend/app/api/health.py`; Test `backend/tests/api/conftest.py`, `backend/tests/api/test_health.py`

`create_app()` 팩토리로 라우터를 등록하고 CORS(Vite dev 5173)를 연다. 이 태스크에서 `schemas.py`를 **00 §5 정본 전체**(`Candle`·`BaseBox`·`RecommendationRow`·`StockDetailResponse`·`PickResult`·`GradeBucket`·`RegimeBucket`·`CurvePoint`·`PerformanceAggregate`·`PerformanceResponse`·`HealthResponse`)로 정의한다(Task 3~5는 이 모듈을 소비). `/health`는 최신 `Run`으로 발행상태/커버리지/신선도를 반환한다(`status` **대문자** `OK|DEGRADED|DOWN`·`reason`·`kis_coverage_pct`·`board_published`·`last_run_date`).

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/conftest.py
import pytest
from datetime import date, datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app.store.models import Base
from app.store.db import get_db
from app.main import create_app


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = SessionTest()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)
```
```python
# backend/tests/api/test_health.py
from datetime import date, datetime
from app.store.models import Run


def test_health_down_when_no_runs(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "DOWN"                 # 00 §5: 대문자
    assert body["reason"]                           # 사유 필드(detail 아님)
    assert body["last_run_date"] is None
    assert body["board_published"] is False
    assert body["kis_coverage_pct"] == 0.0


def test_health_ok_when_latest_run_published(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime(2026, 6, 30, 15, 20),
                       finished_at=datetime(2026, 6, 30, 15, 20, 14), status="OK",
                       kis_coverage_pct=92.0, board_published=True, session_type="정규", reason=None))
    db_session.commit()
    body = client.get("/health").json()
    assert body["status"] == "OK"
    assert body["last_run_date"] == "2026-06-30"
    assert body["kis_coverage_pct"] == 92.0
    assert body["board_published"] is True


def test_health_degraded_when_unpublished(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 29), started_at=datetime(2026, 6, 29, 15, 20),
                       finished_at=datetime(2026, 6, 29, 15, 20, 5), status="UNPUBLISHED",
                       kis_coverage_pct=61.0, board_published=False, session_type="정규",
                       reason="커버리지 61% < 70%"))
    db_session.commit()
    body = client.get("/health").json()
    assert body["status"] == "DEGRADED"
    assert "커버리지" in body["reason"]               # 00 §5: reason
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_health.py -q
# 기대: ModuleNotFoundError: No module named 'app.main'  → 3 errors
```

- [ ] **Step 3: 최소 구현**

```python
# backend/app/api/__init__.py
```
```python
# backend/app/api/schemas.py  (00 §5 정본 — 전 엔드포인트 응답 모델을 한 모듈에 정의)
from __future__ import annotations
from pydantic import BaseModel, ConfigDict   # ConfigDict 는 Task 6 UniverseRow(from_attributes)가 사용

EXIT_LABEL = "익일 오전 VWAP(09:00–10:00)"


class Candle(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: int


class BaseBox(BaseModel):
    start: str
    end: str
    low: float
    high: float


class RecommendationRow(BaseModel):
    rank: int
    ticker: str
    name: str
    market: str
    price_provisional: float
    buy_price_provisional: float
    buy_price_final: float | None = None
    exit_label: str = EXIT_LABEL
    target_price: float
    stop_price: float
    score: float                        # = final
    grade: str                          # S/A/B/C (core 기준)
    badges: list[str] = []              # 신고가/RVOL/수급/시황/베이스
    near_252: float
    near_60: float
    rvol: float
    s_shin: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    spark: list[float] = []
    base_flag: bool
    provisional_flag: bool


class StockDetailResponse(BaseModel):
    ticker: str
    name: str
    price_provisional: float
    grade: str
    final: float
    candles: list[Candle] = []
    high_52w: float
    prior_high: float
    base_box: BaseBox | None = None
    contributions: dict                 # {s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}


class PickResult(BaseModel):
    ticker: str
    name: str
    grade: str
    buy_price_final: float
    vwap_0900_1000: float | None = None
    morning_return: float | None = None
    outcome: str                        # SUCCESS/FAIL/NA
    dart_overnight_flag: bool


class GradeBucket(BaseModel):
    grade: str
    hit_rate: float
    n: int


class RegimeBucket(BaseModel):
    regime: str
    hit_rate: float
    n: int


class CurvePoint(BaseModel):
    date: str
    cum: float


class PerformanceAggregate(BaseModel):
    sample_size: int
    hit_rate: float
    avg_morning_return: float
    cumulative_curve: list[CurvePoint] = []
    by_grade: list[GradeBucket] = []
    by_regime: list[RegimeBucket] = []
    cold_start: bool                    # sample_size < 30


class PerformanceResponse(BaseModel):
    eval_date: str
    picks: list[PickResult] = []
    aggregate: PerformanceAggregate


class HealthResponse(BaseModel):
    status: str                         # 'OK' | 'DEGRADED' | 'DOWN' (대문자)
    reason: str                         # 사유 (필드명 reason, detail 아님)
    kis_coverage_pct: float
    board_published: bool
    last_run_date: str | None = None
```
```python
# backend/app/api/health.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Run
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    last_run = db.scalars(select(Run).order_by(Run.run_date.desc()).limit(1)).first()
    if last_run is None:
        return HealthResponse(status="DOWN", reason="런 기록 없음",
                              kis_coverage_pct=0.0, board_published=False, last_run_date=None)
    if last_run.status == "OK" and last_run.board_published:
        status, reason = "OK", "정상"
    else:
        status, reason = "DEGRADED", (last_run.reason or last_run.status)
    return HealthResponse(
        status=status,
        reason=reason,
        kis_coverage_pct=last_run.kis_coverage_pct or 0.0,
        board_published=bool(last_run.board_published),
        last_run_date=last_run.run_date.isoformat(),
    )
```
```python
# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health


def create_app() -> FastAPI:
    app = FastAPI(title="closing-bet-recommender", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    return app


app = create_app()
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_health.py -q
# 기대: 3 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/main.py backend/app/api/__init__.py backend/app/api/schemas.py backend/app/api/health.py backend/tests/api/conftest.py backend/tests/api/test_health.py
git commit -m "feat(api): FastAPI 앱 팩토리 + GET /health + 00 §5 응답 스키마 정본

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: `GET /recommendations/{run_date}` (`api/recommendations.py`)

> **[00 §5 정본]** `RecommendationRow`에 `spark: list[float]`·`base_flag: bool`(+`score`=final·`exit_label`·`badges`) 포함. 응답 `{run_date, session_type, data_available, kis_coverage_pct, regimes: dict[str,RegimeInfo], recommendations: [...]}` (Task 8b `RunResult` 소비).

**Files:** Modify `backend/app/api/schemas.py`, `backend/app/main.py`; Create `backend/app/api/recommendations.py`; Test `backend/tests/api/test_recommendations.py`

추천 보드 + 레짐 게이지를 반환한다. 응답은 **00 §5 정본** `{run_date, session_type, data_available, kis_coverage_pct, regimes: dict[str,RegimeInfo], recommendations: list[RecommendationRow]}` (Task 8b `RunResult`가 영속화한 `runs`/`recommendations`/`regime_snapshots`를 소비). 각 `RecommendationRow`는 `score`(=final)·`grade`(core 기준)·`spark`·`base_flag`·`exit_label`·`badges`를 포함한다. 정렬은 `rank` 오름차순. 미발행/저레짐이면 `recommendations`는 비고, `data_available`은 KIS 커버리지>0 여부로 판정한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_recommendations.py
from datetime import date, datetime
from app.store.models import Recommendation, RegimeSnapshot, Run


def _rec(**kw):
    base = dict(run_date=date(2026, 6, 30), ticker="000660", name="SK하이닉스", market="KOSPI",
                rank=1, price_provisional=24500.0, buy_price_provisional=24500.0, buy_price_final=None,
                s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03, regime_mult=1.0, veto=1,
                core=1.12, final=1.12, grade="S", near_252=1.02, near_60=1.04, rvol=2.5,
                target_price=25200.0, stop_price=23800.0, spark=[1.0, 2.0, 3.0], base_flag=True,
                provisional_flag=True, created_at=datetime.now())
    base.update(kw)
    return Recommendation(**base)


def _published_run(d=date(2026, 6, 30), coverage=90.0):
    return Run(run_date=d, started_at=datetime.now(), finished_at=datetime.now(), status="OK",
               kis_coverage_pct=coverage, board_published=True, session_type="정규", reason=None)


def _regime(market="KOSPI", regime_mult=1.0):
    return RegimeSnapshot(run_date=date(2026, 6, 30), market=market, index_level=2700.0,
                          ma5=2680.0, ma5_prev=2670.0, cond_a=True, cond_b=True, regime_mult=regime_mult)


def test_recommendations_returns_ranked_rows_and_regime_dict(client, db_session):
    db_session.add(_published_run())
    db_session.add(_rec(rank=2, ticker="005930", name="삼성전자", core=0.55, final=0.55, grade="B"))
    db_session.add(_rec(rank=1))
    db_session.add(_regime())
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["run_date"] == "2026-06-30"
    assert body["session_type"] == "정규"
    assert body["data_available"] is True
    assert body["kis_coverage_pct"] == 90.0
    assert [r["rank"] for r in body["recommendations"]] == [1, 2]   # rank 오름차순
    assert body["recommendations"][0]["grade"] == "S"
    assert body["recommendations"][0]["score"] == 1.12             # score = final
    # 00 §5: regimes 는 dict[str, RegimeInfo] (시장 키)
    assert isinstance(body["regimes"], dict)
    assert body["regimes"]["KOSPI"]["regime_mult"] == 1.0


def test_recommendations_response_schema_has_spark_and_base_flag(client, db_session):
    """00 §5 정본: RecommendationRow 에 spark/base_flag/score/exit_label/badges 존재."""
    db_session.add(_published_run())
    db_session.add(_rec(rank=1))
    db_session.add(_regime())
    db_session.commit()
    row = client.get("/recommendations/2026-06-30").json()["recommendations"][0]
    assert "spark" in row and isinstance(row["spark"], list) and row["spark"] == [1.0, 2.0, 3.0]
    assert "base_flag" in row and row["base_flag"] is True
    assert row["score"] == 1.12                                    # = final
    assert row["exit_label"].startswith("익일 오전 VWAP")
    assert "badges" in row and isinstance(row["badges"], list)


def test_recommendations_empty_board_keeps_data_available(client, db_session):
    """저레짐으로 추천 0이어도 data_available=true (00 §5)."""
    db_session.add(_published_run(coverage=88.0))
    db_session.add(_regime(market="KOSPI", regime_mult=0.0))
    db_session.add(_regime(market="KOSDAQ", regime_mult=0.0))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["data_available"] is True
    assert body["recommendations"] == []
    assert body["regimes"]["KOSPI"]["regime_mult"] == 0.0


def test_recommendations_unpublished_run_has_no_rows(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime.now(), finished_at=datetime.now(),
                       status="UNPUBLISHED", kis_coverage_pct=61.0, board_published=False,
                       session_type="정규", reason="커버리지 61% < 70%"))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["recommendations"] == []
    assert body["kis_coverage_pct"] == 61.0
    assert body["data_available"] is True       # 커버리지>0 → KIS 데이터는 수신됨
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_recommendations.py -q
# 기대: 404 또는 ImportError → 4 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py`에 추가:

```python
# backend/app/api/schemas.py  (Task 3 추가 — /recommendations 래퍼; 00 §3 RegimeInfo)


class RegimeInfo(BaseModel):            # 00 §3 RegimeInfo — 시장별 레짐(게이지)
    market: str
    index_level: float
    ma5: float
    regime_mult: float
    cond_a: bool
    cond_b: bool


class RecommendationsResponse(BaseModel):
    run_date: str
    session_type: str | None = None
    data_available: bool
    kis_coverage_pct: float
    regimes: dict[str, RegimeInfo] = {}
    recommendations: list[RecommendationRow] = []
```
```python
# backend/app/api/recommendations.py
from datetime import date
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Recommendation, RegimeSnapshot, Run
from app.api.schemas import RecommendationsResponse, RecommendationRow, RegimeInfo

router = APIRouter(tags=["recommendations"])


def _badges(rec: Recommendation) -> list[str]:
    """00 §5 badges: 신고가/RVOL/수급/시황/베이스 (저장된 신호값에서 결정론적으로 산출)."""
    badges: list[str] = []
    if (rec.near_252 or 0.0) >= 1.0:
        badges.append("신고가")
    if (rec.rvol or 0.0) >= 2.0:
        badges.append("RVOL")
    if (rec.supply_tilt or 0.0) >= 1.0:
        badges.append("수급")
    if (rec.regime_mult or 0.0) >= 1.0:
        badges.append("시황")
    if rec.base_flag:
        badges.append("베이스")
    return badges


def _to_row(rec: Recommendation) -> RecommendationRow:
    # 00 §5 RecommendationRow: score=final, grade=core 기준(저장값), spark/base_flag 포함
    return RecommendationRow(
        rank=rec.rank, ticker=rec.ticker, name=rec.name, market=rec.market,
        price_provisional=rec.price_provisional, buy_price_provisional=rec.buy_price_provisional,
        buy_price_final=rec.buy_price_final, target_price=rec.target_price, stop_price=rec.stop_price,
        score=rec.final, grade=rec.grade, badges=_badges(rec),
        near_252=rec.near_252, near_60=rec.near_60, rvol=rec.rvol,
        s_shin=rec.s_shin, rvol_confirm=rec.rvol_confirm, supply_tilt=rec.supply_tilt,
        regime_mult=rec.regime_mult, veto=rec.veto,
        spark=rec.spark or [], base_flag=rec.base_flag, provisional_flag=rec.provisional_flag,
    )


@router.get("/recommendations/{run_date}", response_model=RecommendationsResponse)
def get_recommendations(run_date: date, db: Session = Depends(get_db)) -> RecommendationsResponse:
    run = db.get(Run, run_date)
    recs = db.scalars(
        select(Recommendation).where(Recommendation.run_date == run_date).order_by(Recommendation.rank)
    ).all()
    regime_rows = db.scalars(
        select(RegimeSnapshot).where(RegimeSnapshot.run_date == run_date)
    ).all()
    regimes = {
        rg.market: RegimeInfo(market=rg.market, index_level=rg.index_level, ma5=rg.ma5,
                              regime_mult=rg.regime_mult, cond_a=rg.cond_a, cond_b=rg.cond_b)
        for rg in regime_rows
    }
    coverage = (run.kis_coverage_pct if run else None) or 0.0
    return RecommendationsResponse(
        run_date=run_date.isoformat(),
        session_type=run.session_type if run else None,
        data_available=coverage > 0.0,
        kis_coverage_pct=coverage,
        regimes=regimes,
        recommendations=[_to_row(r) for r in recs],
    )
```

`main.py`에 라우터 등록:

```python
# backend/app/main.py  (수정)
from app.api import health, recommendations
# ...
    app.include_router(health.router)
    app.include_router(recommendations.router)
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_recommendations.py -q
# 기대: 4 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/schemas.py backend/app/api/recommendations.py backend/app/main.py backend/tests/api/test_recommendations.py
git commit -m "feat(api): GET /recommendations/{date} — 00 §5 정본(regimes dict·spark·base_flag·score)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: `GET /stock/{code}` (`api/stock.py`)

> **[00 §5 정본]** `StockDetailResponse`는 `candles: list[Candle]`·`high_52w`·`prior_high`·`base_box: BaseBox|None` + `contributions`를 **반드시 직렬화**(스펙 §6.5 화면 B 차트). 05가 이 필드들을 소비.

**Files:** Modify `backend/app/main.py`; Create `backend/app/api/stock.py`; Test `backend/tests/api/test_stock.py` (`StockDetailResponse`/`Candle`/`BaseBox`는 Task 2(00 §5)에서 이미 정의)

종목 상세 = **00 §5 `StockDetailResponse`**: `candles: list[Candle]`·`high_52w`·`prior_high`·`base_box: BaseBox|None`(차트) + `contributions{s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}`. 기본은 해당 종목의 **최신 run_date** 추천, `?on=`으로 특정일 조회, 미존재 시 404. 차트 데이터는 주입 경계(`get_chart_provider`) 뒤이므로 테스트는 `dependency_overrides`로 목한다(네트워크 없음). 공급자는 **호출 시점 지연 임포트**라 404(rec 없음) 경로에선 임포트가 일어나지 않는다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_stock.py
from datetime import date, datetime
from app.store.models import Recommendation
from app.api.stock import get_chart_provider


def _rec(d, **kw):
    base = dict(run_date=d, ticker="000660", name="SK하이닉스", market="KOSPI", rank=1,
                price_provisional=24500.0, buy_price_provisional=24500.0, buy_price_final=None,
                s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03, regime_mult=1.0, veto=1,
                core=1.12, final=1.12, grade="S", near_252=1.02, near_60=1.04, rvol=2.5,
                target_price=25200.0, stop_price=23800.0, spark=[1.0, 2.0, 3.0], base_flag=True,
                provisional_flag=True, created_at=datetime.now())
    base.update(kw)
    return Recommendation(**base)


def _fake_chart(code, run_date):
    return {
        "candles": [
            {"date": "2026-06-26", "open": 100.0, "high": 105.0, "low": 99.0, "close": 104.0, "volume": 1000},
            {"date": "2026-06-29", "open": 104.0, "high": 110.0, "low": 103.0, "close": 109.0, "volume": 2000},
        ],
        "high_52w": 120.0,
        "prior_high": 108.0,
        "base_box": {"start": "2026-06-01", "end": "2026-06-20", "low": 95.0, "high": 107.0},
    }


def test_stock_serializes_candles_high_box_and_contributions(client, db_session):
    client.app.dependency_overrides[get_chart_provider] = lambda: _fake_chart
    db_session.add(_rec(date(2026, 6, 29), core=0.7, final=0.7, grade="A"))
    db_session.add(_rec(date(2026, 6, 30), core=1.12, final=1.12, grade="S"))
    db_session.commit()
    body = client.get("/stock/000660").json()
    assert body["grade"] == "S"                        # 최신 run_date
    assert body["final"] == 1.12
    # 00 §5: candles/high_52w/prior_high/base_box 직렬화
    assert len(body["candles"]) == 2
    assert body["candles"][0]["close"] == 104.0
    assert body["high_52w"] == 120.0
    assert body["prior_high"] == 108.0
    assert body["base_box"]["high"] == 107.0
    # contributions {s_shin,rvol_confirm,supply_tilt,regime_mult,veto,core}
    contrib = body["contributions"]
    assert contrib["s_shin"] == 1.16
    assert contrib["rvol_confirm"] == 0.93
    assert contrib["core"] == 1.12


def test_stock_specific_date_query(client, db_session):
    client.app.dependency_overrides[get_chart_provider] = lambda: _fake_chart
    db_session.add(_rec(date(2026, 6, 29), core=0.7, final=0.7, grade="A"))
    db_session.add(_rec(date(2026, 6, 30)))
    db_session.commit()
    body = client.get("/stock/000660?on=2026-06-29").json()
    assert body["grade"] == "A"
    assert body["final"] == 0.7


def test_stock_404_when_missing(client):
    # 차트 공급자 미오버라이드 — 404 가 차트 호출보다 먼저라 지연 임포트도 일어나지 않음
    assert client.get("/stock/999999").status_code == 404
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_stock.py -q
# 기대: 404 미스매치/ImportError → 3 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py` 추가 없음 — `StockDetailResponse`/`Candle`/`BaseBox`는 Task 2(00 §5)에서 정의됨. 차트 데이터는 주입 의존성으로, `contributions`는 저장된 추천행에서 만든다:

```python
# backend/app/api/stock.py
from datetime import date
from typing import Callable
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Recommendation
from app.api.schemas import StockDetailResponse, Candle, BaseBox

router = APIRouter(tags=["stock"])


def get_chart_provider() -> Callable:
    """차트 데이터 공급자(캔들·52주최고·직전고점·베이스박스). 테스트는 dependency_overrides 로 주입.
    실제 구현은 호출 시점 지연 임포트라 404(rec 없음) 경로에선 임포트가 일어나지 않는다."""
    def _provider(code: str, run_date: date) -> dict:
        from app.data.pykrx_client import get_stock_chart
        return get_stock_chart(code, run_date)
    return _provider


@router.get("/stock/{code}", response_model=StockDetailResponse)
def get_stock(code: str, on: date | None = None, db: Session = Depends(get_db),
              chart: Callable = Depends(get_chart_provider)) -> StockDetailResponse:
    stmt = select(Recommendation).where(Recommendation.ticker == code)
    if on is not None:
        stmt = stmt.where(Recommendation.run_date == on)
    stmt = stmt.order_by(Recommendation.run_date.desc()).limit(1)
    rec = db.scalars(stmt).first()
    if rec is None:
        raise HTTPException(status_code=404, detail=f"종목 {code} 추천 이력 없음")

    cd = chart(code, rec.run_date)
    box = cd.get("base_box")
    return StockDetailResponse(
        ticker=rec.ticker, name=rec.name, price_provisional=rec.price_provisional,
        grade=rec.grade, final=rec.final,
        candles=[Candle(**c) for c in cd.get("candles", [])],
        high_52w=cd["high_52w"], prior_high=cd["prior_high"],
        base_box=BaseBox(**box) if box else None,
        contributions={
            "s_shin": rec.s_shin, "rvol_confirm": rec.rvol_confirm, "supply_tilt": rec.supply_tilt,
            "regime_mult": rec.regime_mult, "veto": rec.veto, "core": rec.core,
        },
    )
```

`main.py`에 `from app.api import ..., stock` 추가 + `app.include_router(stock.router)`.

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_stock.py -q
# 기대: 3 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/stock.py backend/app/main.py backend/tests/api/test_stock.py
git commit -m "feat(api): GET /stock/{code} — 00 §5 차트(candles·high_52w·prior_high·base_box)+contributions

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: `GET /performance` (`api/performance.py`)

> **[00 §5 정본]** `PerformanceResponse{eval_date, picks: list[PickResult], aggregate}` 이고 `aggregate`는 `sample_size`·`cumulative_curve: list[CurvePoint]`·`by_grade: list[GradeBucket]`·`by_regime: list[RegimeBucket]`(dict 아님 **배열**)·`cold_start`. 05 PerfAggregate가 `.map` 호출.

**Files:** Modify `backend/app/main.py`; Create `backend/app/api/performance.py`; Test `backend/tests/api/test_performance.py` (`PerformanceResponse`/`PickResult`/`PerformanceAggregate`/`GradeBucket`/`RegimeBucket`/`CurvePoint`는 Task 2(00 §5)에서 정의)

**00 §5 `PerformanceResponse`**{`eval_date`, `picks: list[PickResult]`, `aggregate`}. `aggregate`는 `sample_size`·`hit_rate`·`avg_morning_return`·`cumulative_curve: list[CurvePoint]`·`by_grade: list[GradeBucket]`·`by_regime: list[RegimeBucket]`(**dict 아님 배열**)·`cold_start`(sample_size<30). **N/A는 분모 제외**(적중률=SUCCESS/(SUCCESS+FAIL)).

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_performance.py
from datetime import date, datetime
from app.store.models import Recommendation, Performance


def _rec(rid, grade="S", regime=1.0, ticker="000660"):
    return Recommendation(id=rid, run_date=date(2026, 6, 29), ticker=ticker, name=f"N{ticker}", market="KOSPI",
                          rank=rid, price_provisional=1.0, buy_price_provisional=1.0, buy_price_final=None,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=regime,
                          veto=1, core=1.0, final=1.0, grade=grade, near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=1.1, stop_price=0.9, spark=[1.0, 2.0], base_flag=False,
                          provisional_flag=True, created_at=datetime.now())


def _perf(rid, outcome, ret, vwap=10.0, flag=False):
    return Performance(rec_id=rid, eval_date=date(2026, 6, 30), buy_price_final=10.0,
                       vwap_0900_1000=vwap, morning_return=ret, outcome=outcome,
                       dart_overnight_flag=flag, scored_at=datetime.now())


def test_performance_aggregate_arrays_and_excludes_na(client, db_session):
    db_session.add_all([_rec(1, "S", 1.0, "000660"), _rec(2, "A", 1.0, "005930"), _rec(3, "B", 0.5, "035720")])
    db_session.add_all([
        _perf(1, "SUCCESS", 0.0053, vwap=10.6),
        _perf(2, "FAIL", -0.004, vwap=9.96),
        _perf(3, "NA", None, vwap=None, flag=True),   # 잠김 → 분모 제외
    ])
    db_session.commit()
    body = client.get("/performance").json()
    assert body["eval_date"] == "2026-06-30"
    agg = body["aggregate"]
    assert agg["sample_size"] == 2                # NA 제외
    assert abs(agg["hit_rate"] - 0.5) < 1e-9
    assert agg["cold_start"] is True              # sample_size < 30
    # 00 §5: by_grade/by_regime/cumulative_curve 는 배열(ARRAY)
    assert isinstance(agg["by_grade"], list)
    assert isinstance(agg["by_regime"], list)
    assert isinstance(agg["cumulative_curve"], list)
    grades = {b["grade"]: b for b in agg["by_grade"]}
    assert grades["S"]["hit_rate"] == 1.0 and grades["S"]["n"] == 1
    assert grades["A"]["hit_rate"] == 0.0 and grades["A"]["n"] == 1
    regimes = {b["regime"]: b for b in agg["by_regime"]}
    assert regimes["1.0"]["n"] == 2              # 채점된 2건 모두 regime 1.0
    assert "0.5" not in regimes                  # NA뿐인 레짐 → 분모0 → 버킷 없음
    assert all(("date" in p and "cum" in p) for p in agg["cumulative_curve"])
    picks = {p["ticker"]: p for p in body["picks"]}
    assert picks["035720"]["outcome"] == "NA"
    assert picks["035720"]["dart_overnight_flag"] is True


def test_performance_empty(client):
    body = client.get("/performance").json()
    agg = body["aggregate"]
    assert agg["sample_size"] == 0
    assert agg["cold_start"] is True
    assert agg["by_grade"] == [] and agg["by_regime"] == []
    assert agg["cumulative_curve"] == []
    assert body["picks"] == []
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_performance.py -q
# 기대: ImportError/404 → 2 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py` 추가 없음 — `PerformanceResponse`/`PickResult`/`PerformanceAggregate`/`GradeBucket`/`RegimeBucket`/`CurvePoint`는 Task 2(00 §5)에서 정의됨. 라우터가 등급·레짐 버킷을 **배열**로, 누적곡선을 `CurvePoint` 배열로 만든다:

```python
# backend/app/api/performance.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Recommendation, Performance
from app.api.schemas import (PerformanceResponse, PerformanceAggregate, PickResult,
                             GradeBucket, RegimeBucket, CurvePoint)

router = APIRouter(tags=["performance"])
COLD_START_MIN = 30


@router.get("/performance", response_model=PerformanceResponse)
def get_performance(db: Session = Depends(get_db)) -> PerformanceResponse:
    pairs = db.execute(
        select(Performance, Recommendation)
        .join(Recommendation, Performance.rec_id == Recommendation.id)
        .order_by(Performance.eval_date.desc(), Recommendation.rank)
    ).all()

    picks: list[PickResult] = []
    success = fail = 0
    ret_sum = 0.0
    by_grade: dict[str, list[int]] = {}      # grade -> [success, fail]
    by_regime: dict[str, list[int]] = {}     # regime_mult(str) -> [success, fail]
    curve_by_date: dict = {}                 # eval_date -> sum(morning_return) (채점분)
    latest_eval = None

    for perf, rec in pairs:
        picks.append(PickResult(
            ticker=rec.ticker, name=rec.name, grade=rec.grade,
            buy_price_final=perf.buy_price_final, vwap_0900_1000=perf.vwap_0900_1000,
            morning_return=perf.morning_return, outcome=perf.outcome,
            dart_overnight_flag=perf.dart_overnight_flag,
        ))
        if latest_eval is None or perf.eval_date > latest_eval:
            latest_eval = perf.eval_date
        if perf.outcome == "NA":                          # NA → 분모 제외
            continue
        is_ok = perf.outcome == "SUCCESS"
        success += int(is_ok)
        fail += int(not is_ok)
        if perf.morning_return is not None:
            ret_sum += perf.morning_return
            curve_by_date[perf.eval_date] = curve_by_date.get(perf.eval_date, 0.0) + perf.morning_return
        by_grade.setdefault(rec.grade, [0, 0])[0 if is_ok else 1] += 1
        by_regime.setdefault(f"{rec.regime_mult}", [0, 0])[0 if is_ok else 1] += 1

    sample_size = success + fail
    cum = 0.0
    curve: list[CurvePoint] = []
    for d in sorted(curve_by_date):
        cum += curve_by_date[d]
        curve.append(CurvePoint(date=d.isoformat(), cum=round(cum, 6)))

    aggregate = PerformanceAggregate(
        sample_size=sample_size,
        hit_rate=(success / sample_size) if sample_size else 0.0,
        avg_morning_return=(ret_sum / sample_size) if sample_size else 0.0,
        cumulative_curve=curve,
        by_grade=[GradeBucket(grade=g, hit_rate=s / (s + f), n=s + f) for g, (s, f) in by_grade.items()],
        by_regime=[RegimeBucket(regime=r, hit_rate=s / (s + f), n=s + f) for r, (s, f) in by_regime.items()],
        cold_start=sample_size < COLD_START_MIN,
    )
    return PerformanceResponse(
        eval_date=latest_eval.isoformat() if latest_eval else "",
        picks=picks, aggregate=aggregate,
    )
```

`main.py`에 `performance` 라우터 등록.

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_performance.py -q
# 기대: 2 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/performance.py backend/app/main.py backend/tests/api/test_performance.py
git commit -m "feat(api): GET /performance — 00 §5 정본(eval_date·by_grade/by_regime 배열·cumulative_curve·N/A 분모제외)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: `GET /universe` (`api/universe.py`)

**Files:** Modify `backend/app/api/schemas.py`, `backend/app/main.py`; Create `backend/app/api/universe.py`; Test `backend/tests/api/test_universe.py`

후보 풀 스캐너 = `universe_cache`의 최신 `as_of` 행. eligible 카운트 헤더.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_universe.py
from datetime import date
from app.store.models import UniverseCache


def _u(ticker, as_of, eligible=True, market="KOSPI"):
    return UniverseCache(ticker=ticker, name=f"N{ticker}", market=market, sec_type="보통주",
                         avg_value_20d=1.2e10, is_managed=False, is_warning=False, is_caution=False,
                         listing_days=500, eligible=eligible, as_of=as_of)


def test_universe_returns_latest_as_of_only(client, db_session):
    db_session.add(_u("000660", date(2026, 6, 29)))     # 과거분
    db_session.add(_u("000660", date(2026, 6, 30)))     # 최신
    db_session.add(_u("005930", date(2026, 6, 30), eligible=False))
    db_session.commit()
    body = client.get("/universe").json()
    assert body["as_of"] == "2026-06-30"
    assert body["total"] == 2
    assert body["eligible_count"] == 1
    tickers = {r["ticker"] for r in body["rows"]}
    assert tickers == {"000660", "005930"}


def test_universe_empty(client):
    body = client.get("/universe").json()
    assert body["as_of"] is None
    assert body["total"] == 0
    assert body["rows"] == []
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_universe.py -q
# 기대: ImportError/404 → 2 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py`에 추가:

```python
# backend/app/api/schemas.py  (추가)
class UniverseRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ticker: str
    name: str
    market: str
    sec_type: str
    avg_value_20d: float
    is_managed: bool
    is_warning: bool
    is_caution: bool
    listing_days: int
    eligible: bool
    as_of: date


class UniverseResponse(BaseModel):
    as_of: date | None = None
    total: int = 0
    eligible_count: int = 0
    rows: list[UniverseRow] = []
```
```python
# backend/app/api/universe.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import UniverseCache
from app.api.schemas import UniverseResponse, UniverseRow

router = APIRouter(tags=["universe"])


@router.get("/universe", response_model=UniverseResponse)
def get_universe(db: Session = Depends(get_db)) -> UniverseResponse:
    latest = db.scalars(select(UniverseCache.as_of).order_by(UniverseCache.as_of.desc()).limit(1)).first()
    if latest is None:
        return UniverseResponse()
    rows = db.scalars(
        select(UniverseCache).where(UniverseCache.as_of == latest).order_by(UniverseCache.ticker)
    ).all()
    models = [UniverseRow.model_validate(r) for r in rows]
    return UniverseResponse(
        as_of=latest, total=len(models),
        eligible_count=sum(1 for r in models if r.eligible), rows=models,
    )
```

`main.py`에 `universe` 라우터 등록.

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_universe.py -q
# 기대: 2 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/schemas.py backend/app/api/universe.py backend/app/main.py backend/tests/api/test_universe.py
git commit -m "feat(api): GET /universe 후보풀 스캐너(최신 as_of·eligible 카운트)"
```

---

## Task 7: `GET /backtest` (`api/backtest.py`, 서브시스템 3 의존)

**Files:** Modify `backend/app/api/schemas.py`, `backend/app/main.py`; Create `backend/app/api/backtest.py`; Test `backend/tests/api/test_backtest.py`

백테스트 러너(`app.backtest.engine.run_backtest`, 서브시스템 3)를 **의존성으로 주입**해 호출하고 요약을 반환한다. 테스트는 `dependency_overrides`로 러너를 목 처리(네트워크/실제 백테스트 미실행).

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_backtest.py
from datetime import date
from types import SimpleNamespace
from app.api.backtest import get_backtest_runner
from app.main import create_app
from app.store.db import get_db
from fastapi.testclient import TestClient


def test_backtest_calls_runner_with_range(db_session):
    calls = {}

    def fake_runner(start, end):
        calls["start"], calls["end"] = start, end
        return SimpleNamespace(start=start, end=end, n_picks=120, rank_ic=0.031, t_stat=2.4,
                               hit_rate=0.55, avg_return=0.004, note="D-1 서브셋")

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_backtest_runner] = lambda: fake_runner
    client = TestClient(app)

    body = client.get("/backtest?start=2025-01-01&end=2025-12-31").json()
    assert calls["start"] == date(2025, 1, 1)
    assert calls["end"] == date(2025, 12, 31)
    assert body["n_picks"] == 120
    assert body["rank_ic"] == 0.031
    assert body["t_stat"] == 2.4
    assert body["note"] == "D-1 서브셋"
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_backtest.py -q
# 기대: ModuleNotFoundError: No module named 'app.api.backtest' → 1 error
```

- [ ] **Step 3: 최소 구현**

`schemas.py`에 추가:

```python
# backend/app/api/schemas.py  (추가)
class BacktestResponse(BaseModel):
    start: date
    end: date
    n_picks: int
    rank_ic: float | None = None
    t_stat: float | None = None
    hit_rate: float | None = None
    avg_return: float | None = None
    note: str = ""
```
```python
# backend/app/api/backtest.py
from datetime import date
from typing import Callable
from fastapi import APIRouter, Depends

from app.api.schemas import BacktestResponse

router = APIRouter(tags=["backtest"])


def get_backtest_runner() -> Callable:
    """서브시스템 3의 백테스트 러너를 지연 임포트로 주입(테스트는 override)."""
    from app.backtest.engine import run_backtest
    return run_backtest


@router.get("/backtest", response_model=BacktestResponse)
def get_backtest(start: date, end: date, runner: Callable = Depends(get_backtest_runner)) -> BacktestResponse:
    res = runner(start, end)
    return BacktestResponse(
        start=res.start, end=res.end, n_picks=res.n_picks, rank_ic=res.rank_ic,
        t_stat=res.t_stat, hit_rate=res.hit_rate, avg_return=res.avg_return, note=res.note,
    )
```

`main.py`에 `backtest` 라우터 등록.

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_backtest.py -q
# 기대: 1 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/schemas.py backend/app/api/backtest.py backend/app/main.py backend/tests/api/test_backtest.py
git commit -m "feat(api): GET /backtest 러너 주입 호출(서브시스템3 의존)"
```

---

## Task 8: 장전 스케줄러 — `scheduler/premarket.py` (fail-closed)

> **[00 §2 정본]** 무인자 `health_check()->HealthResult(ok, latest_trading_day, rows, detail)` 소비 — **D-1 외인/기관 수급·거래대금 조회 성공도 검증**(결손 시 `ok=False`→BLOCKED). pykrx D-1 불가 → 런 차단 테스트 추가.

**Files:** Create `backend/app/scheduler/premarket.py`; Test `backend/tests/scheduler/test_premarket.py`

장전 헬스체크 → 통과 시 FINAL prefetch, **실패 시 fail-closed**(prefetch 미호출, `runs.status=BLOCKED`, 알림). 비거래일이면 skip. 콜라보레이터는 모두 주입.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/scheduler/test_premarket.py
from datetime import date, time
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.store.models import Base, Run
from app.scheduler.calendar import TradingCalendar
from app.scheduler import premarket


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _cal():
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close={})


def test_premarket_blocks_and_skips_prefetch_when_health_fails(session_factory):
    prefetch_calls = []
    notify_calls = []
    report = SimpleNamespace(ok=False, latest_trading_day=date(2026, 6, 26), rows=0, detail="pykrx stale")

    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
    )
    assert rc == "BLOCKED"
    assert prefetch_calls == []                       # fail-closed: prefetch 미실행
    assert notify_calls and "stale" in notify_calls[0][1]
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "BLOCKED"
        assert run.board_published is False


def test_premarket_blocks_when_d1_supply_missing(session_factory):
    # 00 §2: health_check() 는 지수 OHLCV뿐 아니라 D-1 외인/기관 수급·거래대금 조회 성공도 검증한다.
    # 수급 결손 → ok=False → fail-closed(BLOCKED·prefetch 미실행).
    prefetch_calls = []
    notify_calls = []
    report = SimpleNamespace(ok=False, latest_trading_day=date(2026, 6, 26), rows=0,
                             detail="D-1 외인/기관 수급 결손")
    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
    )
    assert rc == "BLOCKED"
    assert prefetch_calls == []                        # 수급 결손 → prefetch 미실행
    assert notify_calls and "수급" in notify_calls[0][1]
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "BLOCKED" and run.board_published is False
        assert "수급" in run.reason


def test_premarket_prefetches_when_health_ok(session_factory):
    prefetch_calls = []
    report = SimpleNamespace(ok=True, latest_trading_day=date(2026, 6, 29), rows=2700, detail="ok")
    rc = premarket.run_premarket(
        date(2026, 6, 30), calendar=_cal(),
        health_check=lambda: report,
        prefetch_final=lambda d: prefetch_calls.append(d),
        session_factory=session_factory,
        notify=lambda t, m: None,
    )
    assert rc == "OK"
    assert prefetch_calls == [date(2026, 6, 30)]


def test_premarket_skips_non_trading_day(session_factory):
    rc = premarket.run_premarket(
        date(2026, 7, 1), calendar=_cal(),
        health_check=lambda: (_ for _ in ()).throw(AssertionError("health 호출 금지")),
        prefetch_final=lambda d: None, session_factory=session_factory, notify=lambda t, m: None,
    )
    assert rc is None
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/scheduler/test_premarket.py -q
# 기대: AttributeError: module 'app.scheduler.premarket' has no attribute 'run_premarket' → 4 failed/errors
```

- [ ] **Step 3: 최소 구현**

```python
# backend/app/scheduler/premarket.py
from __future__ import annotations
import logging
from datetime import date, datetime
from app.scheduler.calendar import TradingCalendar, load_default_calendar

logger = logging.getLogger(__name__)


def _desktop_notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        logger.info("[NOTIFY] %s: %s", title, message)


def _record_run(db, run_date, *, status, published, reason, session_type, started):
    from app.store.models import Run
    run = db.get(Run, run_date)
    if run is None:
        run = Run(run_date=run_date, started_at=started)
        db.add(run)
    run.finished_at = datetime.now()
    run.status = status
    run.board_published = published
    run.reason = reason
    run.session_type = session_type
    run.kis_coverage_pct = run.kis_coverage_pct  # 장전엔 미상


def run_premarket(run_date: date | None = None, *, calendar: TradingCalendar | None = None,
                  health_check=None, prefetch_final=None, session_factory=None, notify=None):
    calendar = calendar or load_default_calendar()
    run_date = run_date or datetime.now().date()
    if not calendar.is_trading_day(run_date):
        logger.info("non-trading day %s, premarket skip", run_date)
        return None

    if health_check is None or prefetch_final is None:
        from app.data import pykrx_client
        health_check = health_check or pykrx_client.health_check
        prefetch_final = prefetch_final or pykrx_client.prefetch_final
    if session_factory is None:
        from app.store.db import SessionLocal as session_factory
    notify = notify or _desktop_notify

    started = datetime.now()
    report = health_check()        # 00 §2: 지수 OHLCV + D-1 외인/기관 수급·거래대금까지 검증한 무인자 결과
    if not report.ok:
        with session_factory() as db:
            _record_run(db, run_date, status="BLOCKED", published=False,
                        reason=f"프리오픈 헬스체크 실패: {report.detail}",
                        session_type=calendar.session_type(run_date), started=started)
            db.commit()
        notify("종가베팅 프리오픈 실패(fail-closed)", report.detail)
        return "BLOCKED"

    prefetch_final(run_date)
    logger.info("premarket prefetch done for %s", run_date)
    return "OK"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_premarket()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/scheduler/test_premarket.py -q
# 기대: 4 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/scheduler/premarket.py backend/tests/scheduler/test_premarket.py
git commit -m "feat(scheduler): 장전 prefetch + 헬스체크 fail-closed(00 §2 D-1 수급 포함·BLOCKED·알림)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8b: 오케스트레이터 — `engine/orchestrator.py` (B2·M4 해소: 후보풀·시장별 레짐·MODELED RVOL 생산자·EngineRow→RecRow)

> **[00 §3 정본]** 플랜02의 **순수** `run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg_by_ticker, veto_by_ticker, max_emit)->PipelineResult(published, reason, rows, coverage_pct)` 을 감싸 데이터 수집·레짐 산출/영속화·**15:20 거래량 스냅샷 upsert + trailing≥20 평균(MODELED RVOL 생산자)**·veto 맵·`EngineRow→RecRow`·`coverage×100`을 수행한다. daily_run(Task 9)은 **이 `orchestrate_run`만** 호출한다. (RecRow/RegimeInfo/RunResult 필드는 00 §3 그대로.)

**Files:** Create `backend/app/engine/orchestrator.py`; Test `backend/tests/engine/test_orchestrator.py`

- [ ] **Step 1: 실패 테스트 작성** (페이크 adapter/store + run_pipeline 주입 — 풀 union·시장별 레짐·RVOL≥20 임계·coverage×100·RecRow 매핑 고정)
```python
# backend/tests/engine/test_orchestrator.py
from datetime import date, datetime
from app.engine.orchestrator import orchestrate_run, RunResult, RecRow, RegimeInfo, compute_modeled_avg

class FakeAdapter:
    def d1_value_top(self, run_date, n): return ["000660", "005930"]           # D-1 거래대금 상위(혼합시장)
    def live_value_top(self, market, top): return ["111111"] if market == "KOSDAQ" else ["005930"]
    def market_of(self, t): return {"000660": "KOSDAQ", "005930": "KOSPI", "111111": "KOSDAQ"}[t]
    def static_ok(self, t): return True
    def quote(self, t):
        return type("Q", (), {"ticker": t, "price": 100.0, "cum_volume": 1000, "cum_value": 1.0e8,
                              "change_pct": 1.0, "is_halted": False, "is_limit_up": False, "is_vi": False})()
    def regime_inputs(self, market):  # (index_level, prev5_closes) → compute_regime
        return (350.0, [349, 348, 347, 346, 345]) if market == "KOSDAQ" else (2600.0, [2650, 2655, 2660, 2665, 2670])
    def net_purchase(self, t): return 0.0
    def avg_value_20d(self, t): return 5.0e8
    def veto(self, t, snapshot_at): return 0 if t == "000660" else 1          # 000660 희석 veto

class DictStore:                                                              # 인메모리 store 페이크
    def __init__(self): self.vol = []; self.regimes = []
    def upsert_volume_snapshot(self, ticker, d, cum_volume, cum_value): self.vol.append((ticker, d, cum_value))
    def trailing_volume(self, ticker, before): return [v for (tk, _, v) in self.vol if tk == ticker]
    def save_regime(self, run_date, market, info): self.regimes.append((market, info))

def fake_run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg_by_ticker, veto_by_ticker, max_emit):
    rows = []
    for t in candidates:
        if veto_by_ticker.get(t, 1) == 0: continue                            # veto 탈락
        rm = regime_by_market[FakeAdapter().market_of(t)]
        if rm == 0.0: continue                                                # 레짐 게이트
        rows.append(type("E", (), {"ticker": t, "name": "N", "market": FakeAdapter().market_of(t),
            "price": 100.0, "buy": 100.0, "s_shin": 1.0, "s_geo": 0.8, "rvol_confirm": 0.9, "supply_tilt": 1.0,
            "regime_mult": rm, "veto": 1, "core": 0.9, "final": 0.9 * rm, "grade": "A", "near_252": 1.0,
            "near_60": 1.0, "rvol": 2.0, "target": 103.0, "stop": 97.0, "spark": [1, 2, 3], "base_flag": False})())
    return type("PR", (), {"published": bool(rows), "reason": None, "rows": rows, "coverage_pct": 1.0})()

def test_orchestrate_pool_regime_coverage():
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=FakeAdapter(), store=DictStore(), run_pipeline_fn=fake_run_pipeline)
    assert isinstance(res, RunResult) and res.data_available is True
    emitted = {r.ticker for r in res.recommendations}
    assert "005930" in emitted and "000660" not in emitted                    # 풀 union + veto 탈락
    assert res.kis_coverage_pct == 100.0                                      # 0~1 ×100
    assert set(res.regimes) == {"KOSPI", "KOSDAQ"}                            # 시장별 RegimeInfo
    assert all(isinstance(r, RecRow) for r in res.recommendations)            # EngineRow→RecRow

def test_modeled_rvol_threshold():
    assert compute_modeled_avg([1.0e8] * 19, min_sessions=20) is None         # <20세션 → 중립
    assert compute_modeled_avg([1.0e8] * 20, min_sessions=20) == 1.0e8        # ≥20세션 → 평균
```

- [ ] **Step 2: 실패 확인** — `cd backend && python -m pytest tests/engine/test_orchestrator.py -q` → `ModuleNotFoundError: app.engine.orchestrator`

- [ ] **Step 3: 최소 구현**
```python
# backend/app/engine/orchestrator.py
from dataclasses import dataclass
from datetime import date, datetime
from app.engine.pipeline import run_pipeline as _run_pipeline
from app.engine.signals.regime import compute_regime

@dataclass
class RegimeInfo:
    market: str; index_level: float; ma5: float; regime_mult: float; cond_a: bool; cond_b: bool

@dataclass
class RecRow:
    rank: int; ticker: str; name: str; market: str
    price_provisional: float; buy_price_provisional: float; buy_price_final: float | None
    target_price: float; stop_price: float
    s_shin: float; s_geo: float; rvol_confirm: float; supply_tilt: float
    regime_mult: float; veto: int; core: float; final: float; grade: str
    near_252: float; near_60: float; rvol: float
    spark: list; base_flag: bool; provisional_flag: bool = True

@dataclass
class RunResult:
    run_date: date; session_type: str; data_available: bool; kis_coverage_pct: float
    recommendations: list; regimes: dict; reason: str | None = None

def compute_modeled_avg(trailing_values, min_sessions=20):
    """trailing ≥min_sessions 이면 평균, 미만이면 None(=rvol_confirm 중립 1.0). (M4 RVOL 생산자)"""
    if len(trailing_values) < min_sessions:
        return None
    return sum(trailing_values) / len(trailing_values)

def orchestrate_run(run_date, snapshot_at, *, adapter, store, run_pipeline_fn=_run_pipeline,
                    d1_top_n=200, live_top=30, rvol_min_sessions=20, session_type="정규", max_emit=30):
    # ① 후보풀 = D-1 거래대금 top-N ∪ 라이브 top-30×2
    pool = list(dict.fromkeys(
        adapter.d1_value_top(run_date, d1_top_n)
        + adapter.live_value_top("KOSPI", live_top) + adapter.live_value_top("KOSDAQ", live_top)))
    # ② 정적 위생 → ③ 라이브 시세 → ④ 동적 위생
    quotes = {}
    for t in (x for x in pool if adapter.static_ok(x)):
        q = adapter.quote(t)
        if q is None:
            continue
        if q.is_halted or q.is_limit_up or q.is_vi or q.change_pct >= 20.0:   # 동적 과열/정지 제거
            continue
        quotes[t] = q
    candidates = list(quotes)
    coverage = (len(quotes) / len(pool)) if pool else 0.0
    # ⑤ 시장별 레짐 산출 + 영속화 (종목 소속시장)
    regimes = {}
    for market in ("KOSPI", "KOSDAQ"):
        idx, prev5 = adapter.regime_inputs(market)
        rm = compute_regime(idx, prev5)
        ma5 = sum(prev5) / len(prev5)
        info = RegimeInfo(market, idx, ma5, rm, idx >= ma5, prev5[-1] > prev5[0])
        regimes[market] = info
        store.save_regime(run_date, market, info)
    regime_by_market = {m: r.regime_mult for m, r in regimes.items()}
    # ⑥ MODELED RVOL 생산자: 당일 스냅샷 upsert + trailing≥20 평균
    modeled_avg = {}
    for t, q in quotes.items():
        store.upsert_volume_snapshot(t, run_date, q.cum_volume, q.cum_value)
        modeled_avg[t] = compute_modeled_avg(store.trailing_volume(t, run_date), rvol_min_sessions)
    # ⑦ veto 맵
    veto_by_ticker = {t: adapter.veto(t, snapshot_at) for t in candidates}
    # ⑧ 순수 엔진 호출 → EngineRow→RecRow, coverage×100
    fetch_live = lambda t: quotes[t]
    pr = run_pipeline_fn(candidates, fetch_live, regime_by_market, modeled_avg, veto_by_ticker, max_emit)
    recs = [RecRow(rank=i + 1, ticker=e.ticker, name=e.name, market=e.market,
                   price_provisional=e.price, buy_price_provisional=e.buy, buy_price_final=None,
                   target_price=e.target, stop_price=e.stop, s_shin=e.s_shin, s_geo=e.s_geo,
                   rvol_confirm=e.rvol_confirm, supply_tilt=e.supply_tilt, regime_mult=e.regime_mult,
                   veto=e.veto, core=e.core, final=e.final, grade=e.grade, near_252=e.near_252,
                   near_60=e.near_60, rvol=e.rvol, spark=e.spark, base_flag=e.base_flag)
            for i, e in enumerate(pr.rows)]
    return RunResult(run_date=run_date, session_type=session_type,
                     data_available=bool(quotes), kis_coverage_pct=round(coverage * 100, 1),
                     recommendations=recs, regimes=regimes, reason=pr.reason)
```

- [ ] **Step 4: 통과 확인** — `cd backend && python -m pytest tests/engine/test_orchestrator.py -q` → PASS

- [ ] **Step 5: 커밋**
```bash
git add backend/app/engine/orchestrator.py backend/tests/engine/test_orchestrator.py
git commit -m "feat(engine): orchestrate_run — 후보풀·시장별레짐·MODELED RVOL 생산자·EngineRow→RecRow (B2·M4)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: 15:20 런 스케줄러 — `scheduler/daily_run.py` (커버리지 게이트·top3 알림)

**Files:** Create `backend/app/scheduler/daily_run.py`; Test `backend/tests/scheduler/test_daily_run.py`

**[00 §3]** `orchestrate_run(run_date, snapshot_at, adapter=..., store=...)` 호출(Task 8b) → `data_available=False` 또는 `kis_coverage_pct<70` → **미발행(UNPUBLISHED)**, 아니면 추천/레짐 영속화 + JSON 스냅샷 + `runs.status=OK` + top3 알림. 스냅샷 시각은 캘린더(특수세션=마감−10).

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/scheduler/test_daily_run.py
from datetime import date, datetime, time
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.store.models import Base, Run, Recommendation, RegimeSnapshot
from app.scheduler.calendar import TradingCalendar
from app.scheduler import daily_run


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _rec_row(rank, ticker, name, grade="S"):
    return SimpleNamespace(rank=rank, ticker=ticker, name=name, market="KOSPI",
                           price_provisional=24500.0, buy_price_provisional=24500.0,
                           s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03,
                           regime_mult=1.0, veto=1, core=1.12, final=1.12, grade=grade,
                           near_252=1.02, near_60=1.04, rvol=2.5, target_price=25200.0,
                           stop_price=23800.0, provisional_flag=True)


def _result(coverage=90.0, data_available=True, recs=None):
    regimes = {"KOSPI": SimpleNamespace(market="KOSPI", index_level=2700.0, ma5=2680.0,
                                        ma5_prev=2670.0, cond_a=True, cond_b=True, regime_mult=1.0)}
    return SimpleNamespace(run_date=date(2026, 6, 30), session_type="정규",
                           data_available=data_available, kis_coverage_pct=coverage,
                           recommendations=recs if recs is not None else [], regimes=regimes)


def _cal(early=None):
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close=early or {})


def test_daily_run_publishes_and_persists_top3(session_factory):
    captured_snapshot_at = {}
    notify_calls = []
    snap_calls = []
    recs = [_rec_row(1, "000660", "SK하이닉스"), _rec_row(2, "005930", "삼성전자", "A"),
            _rec_row(3, "035720", "카카오", "B"), _rec_row(4, "068270", "셀트리온", "C")]

    def fake_pipeline(run_date, snapshot_at):
        captured_snapshot_at["t"] = snapshot_at
        return _result(recs=recs)

    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=fake_pipeline, session_factory=session_factory,
        notify=lambda t, m: notify_calls.append((t, m)),
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: snap_calls.append((d, p))),
    )
    assert rc == "OK"
    # 스냅샷 시각 = 정규일 15:20 (15:20–15:30 창)
    assert captured_snapshot_at["t"] == datetime(2026, 6, 30, 15, 20)
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "OK" and run.board_published is True and run.kis_coverage_pct == 90.0
        saved = db.scalars(select(Recommendation).order_by(Recommendation.rank)).all()
        assert [r.ticker for r in saved] == ["000660", "005930", "035720", "068270"]
        assert db.scalars(select(RegimeSnapshot)).first().market == "KOSPI"
    # top3만 알림
    assert len(notify_calls) == 1
    msg = notify_calls[0][1]
    assert "셀트리온" not in msg and "SK하이닉스" in msg
    assert snap_calls and snap_calls[0][0] == date(2026, 6, 30)


def test_daily_run_unpublished_when_coverage_below_floor(session_factory):
    snap_calls = []
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: _result(coverage=65.0, recs=[_rec_row(1, "000660", "SK")]),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: snap_calls.append(d)),
    )
    assert rc == "UNPUBLISHED"
    with session_factory() as db:
        run = db.get(Run, date(2026, 6, 30))
        assert run.status == "UNPUBLISHED" and run.board_published is False
        assert "커버리지" in run.reason
        assert db.scalars(select(Recommendation)).all() == []   # 영속화 금지
    assert snap_calls == []                                      # 스냅샷 미작성


def test_daily_run_unpublished_when_kis_fully_down(session_factory):
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: _result(data_available=False, coverage=0.0),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
    )
    assert rc == "UNPUBLISHED"
    with session_factory() as db:
        assert "미수신" in db.get(Run, date(2026, 6, 30)).reason


def test_daily_run_special_session_snapshot_minus_10(session_factory):
    cap = {}
    daily_run.run_daily(
        date(2026, 9, 29), calendar=_cal(early={date(2026, 9, 29): time(14, 0)}),
        run_pipeline=lambda d, s: cap.setdefault("t", s) or _result(coverage=80.0,
            recs=[_rec_row(1, "000660", "SK")]),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
    )
    assert cap["t"] == datetime(2026, 9, 29, 13, 50)            # 마감14:00 − 10분
    with session_factory() as db:
        assert db.get(Run, date(2026, 9, 29)).session_type == "특수"


def test_daily_run_skips_non_trading_day(session_factory):
    rc = daily_run.run_daily(
        date(2026, 7, 1), calendar=_cal(),
        run_pipeline=lambda d, s: (_ for _ in ()).throw(AssertionError("pipeline 호출 금지")),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None),
    )
    assert rc is None
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/scheduler/test_daily_run.py -q
# 기대: AttributeError: ... has no attribute 'run_daily' → 5 failed/errors
```

- [ ] **Step 3: 최소 구현**

```python
# backend/app/scheduler/daily_run.py
from __future__ import annotations
import logging
from datetime import date, datetime
from app.scheduler.calendar import TradingCalendar, load_default_calendar

logger = logging.getLogger(__name__)
MIN_COVERAGE_PCT = 70.0     # 발행 게이트 바닥 (아키텍처 §5)
TOP_N_NOTIFY = 3


def _desktop_notify(title: str, message: str) -> None:
    try:
        from plyer import notification
        notification.notify(title=title, message=message, timeout=10)
    except Exception:
        logger.info("[NOTIFY] %s: %s", title, message)


def _upsert_run(db, run_date, *, status, published, coverage, session_type, reason, started):
    from app.store.models import Run
    run = db.get(Run, run_date)
    if run is None:
        run = Run(run_date=run_date, started_at=started)
        db.add(run)
    run.finished_at = datetime.now()
    run.status = status
    run.board_published = published
    run.kis_coverage_pct = coverage
    run.session_type = session_type
    run.reason = reason


def _persist_recs(db, run_date, result):
    from app.store.models import Recommendation
    db.query(Recommendation).filter(Recommendation.run_date == run_date).delete()
    now = datetime.now()
    for r in result.recommendations:
        db.add(Recommendation(
            run_date=run_date, ticker=r.ticker, name=r.name, market=r.market, rank=r.rank,
            price_provisional=r.price_provisional, buy_price_provisional=r.buy_price_provisional,
            buy_price_final=None, s_shin=r.s_shin, s_geo=r.s_geo, rvol_confirm=r.rvol_confirm,
            supply_tilt=r.supply_tilt, regime_mult=r.regime_mult, veto=r.veto, core=r.core,
            final=r.final, grade=r.grade, near_252=r.near_252, near_60=r.near_60, rvol=r.rvol,
            target_price=r.target_price, stop_price=r.stop_price, provisional_flag=True, created_at=now,
        ))


def _persist_regimes(db, run_date, result):
    from app.store.models import RegimeSnapshot
    db.query(RegimeSnapshot).filter(RegimeSnapshot.run_date == run_date).delete()
    for rg in result.regimes.values():
        db.add(RegimeSnapshot(
            run_date=run_date, market=rg.market, index_level=rg.index_level, ma5=rg.ma5,
            ma5_prev=rg.ma5_prev, cond_a=rg.cond_a, cond_b=rg.cond_b, regime_mult=rg.regime_mult,
        ))


def _payload(run_date, result):
    return {
        "run_date": run_date.isoformat(),
        "session_type": result.session_type,
        "kis_coverage_pct": result.kis_coverage_pct,
        "recommendations": [vars(r) for r in result.recommendations],
        "regimes": [vars(rg) for rg in result.regimes.values()],
    }


def _notify_top3(result, notify):
    top = sorted(result.recommendations, key=lambda r: r.rank)[:TOP_N_NOTIFY]
    if not top:
        return
    body = ", ".join(f"{r.name}({r.ticker}) {r.grade}" for r in top)
    notify("종가베팅 추천 발행", body)


def run_daily(run_date: date | None = None, *, calendar: TradingCalendar | None = None,
              run_pipeline=None, session_factory=None, notify=None, snapshots=None):
    calendar = calendar or load_default_calendar()
    run_date = run_date or datetime.now().date()
    if not calendar.is_trading_day(run_date):
        logger.info("non-trading day %s, daily_run skip", run_date)
        return None

    if run_pipeline is None:
        from app.engine.pipeline import run_pipeline
    if session_factory is None:
        from app.store.db import SessionLocal as session_factory
    if snapshots is None:
        from app.store import snapshots
    notify = notify or _desktop_notify

    snapshot_at = calendar.snapshot_at(run_date)         # 정규=15:20 / 특수=마감−10
    session_type = calendar.session_type(run_date)
    started = datetime.now()
    result = run_pipeline(run_date, snapshot_at)

    with session_factory() as db:
        if not result.data_available:
            _upsert_run(db, run_date, status="UNPUBLISHED", published=False,
                        coverage=result.kis_coverage_pct, session_type=session_type,
                        reason="KIS 데이터 미수신(EOD 프록시 금지)", started=started)
            db.commit()
            return "UNPUBLISHED"
        if result.kis_coverage_pct < MIN_COVERAGE_PCT:
            _upsert_run(db, run_date, status="UNPUBLISHED", published=False,
                        coverage=result.kis_coverage_pct, session_type=session_type,
                        reason=f"커버리지 {result.kis_coverage_pct:.0f}% < {MIN_COVERAGE_PCT:.0f}%",
                        started=started)
            db.commit()
            return "UNPUBLISHED"
        _persist_recs(db, run_date, result)
        _persist_regimes(db, run_date, result)
        _upsert_run(db, run_date, status="OK", published=True, coverage=result.kis_coverage_pct,
                    session_type=session_type, reason=None, started=started)
        db.commit()

    snapshots.write_snapshot(run_date, _payload(run_date, result))
    _notify_top3(result, notify)
    return "OK"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_daily()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/scheduler/test_daily_run.py -q
# 기대: 5 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/scheduler/daily_run.py backend/tests/scheduler/test_daily_run.py
git commit -m "feat(scheduler): 15:20 런 파이프라인(특수세션·커버리지게이트·top3알림·JSON스냅샷)"
```

---

## Task 10: 익일 채점 스케줄러 — `scheduler/scoring_job.py` (N/A·DART 재스캔·룩어헤드 가드)

**Files:** Create `backend/app/scheduler/scoring_job.py`; Test `backend/tests/scheduler/test_scoring_job.py`

익일 09~10시 채점: `run_date=prev_trading_day(eval_date)`. 매수가=**확정 종가 close[run_date]**, 청산=**오전 VWAP(eval_date)**. VWAP None → outcome=NA(분모 제외). DART 오버나잇 재스캔 플래그. **룩어헤드 가드**: close는 run_date, VWAP는 t+1(eval_date)로만 조회.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/scheduler/test_scoring_job.py
from datetime import date, datetime, time
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from app.store.models import Base, Recommendation, Performance
from app.scheduler.calendar import TradingCalendar
from app.scheduler import scoring_job


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _rec(db, rid, ticker, run_date=date(2026, 6, 29)):
    db.add(Recommendation(id=rid, run_date=run_date, ticker=ticker, name=f"N{ticker}", market="KOSPI",
                          rank=rid, price_provisional=10.0, buy_price_provisional=10.0, buy_price_final=None,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=1.0, veto=1,
                          core=1.0, final=1.0, grade="S", near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=11.0, stop_price=9.0, provisional_flag=True, created_at=datetime.now()))


def _cal():
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close={})


def test_scoring_marks_success_fail_and_na(session_factory):
    with session_factory() as db:
        _rec(db, 1, "AAA"); _rec(db, 2, "BBB"); _rec(db, 3, "CCC")
        db.commit()

    closes = {"AAA": 10.0, "BBB": 10.0, "CCC": 10.0}
    vwaps = {"AAA": 10.6, "BBB": 9.95, "CCC": None}    # CCC: 잠김 → NA
    dart = {"BBB"}

    scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory,
        fetch_confirmed_close=lambda t, d: closes[t],
        fetch_morning_vwap=lambda t, d: vwaps[t],
        overnight_scan=lambda t, since, until: t in dart,
    )
    with session_factory() as db:
        perfs = {p.rec_id: p for p in db.scalars(select(Performance)).all()}
        assert perfs[1].outcome == "SUCCESS" and perfs[1].morning_return > 0
        assert perfs[2].outcome == "FAIL" and perfs[2].dart_overnight_flag is True
        assert perfs[3].outcome == "NA" and perfs[3].morning_return is None
        # 확정 종가가 buy_price_final로 반영
        assert db.get(Recommendation, 1).buy_price_final == 10.0


def test_scoring_no_lookahead_uses_t_for_close_and_t_plus_1_for_vwap(session_factory):
    with session_factory() as db:
        _rec(db, 1, "AAA", run_date=date(2026, 6, 29))
        db.commit()
    close_args, vwap_args = [], []
    scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory,
        fetch_confirmed_close=lambda t, d: close_args.append(d) or 10.0,
        fetch_morning_vwap=lambda t, d: vwap_args.append(d) or 10.5,
        overnight_scan=lambda t, s, u: False,
    )
    assert close_args == [date(2026, 6, 29)]    # close[t]
    assert vwap_args == [date(2026, 6, 30)]     # VWAP[t+1]
    assert close_args[0] < vwap_args[0]          # 룩어헤드 없음


def test_scoring_is_idempotent(session_factory):
    with session_factory() as db:
        _rec(db, 1, "AAA"); db.commit()
    kw = dict(calendar=_cal(), session_factory=session_factory,
              fetch_confirmed_close=lambda t, d: 10.0, fetch_morning_vwap=lambda t, d: 10.5,
              overnight_scan=lambda t, s, u: False)
    scoring_job.run_scoring(date(2026, 6, 30), **kw)
    scoring_job.run_scoring(date(2026, 6, 30), **kw)   # 재실행
    with session_factory() as db:
        assert len(db.scalars(select(Performance)).all()) == 1   # 중복 채점 금지
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/scheduler/test_scoring_job.py -q
# 기대: AttributeError: ... has no attribute 'run_scoring' → 3 failed/errors
```

- [ ] **Step 3: 최소 구현**

```python
# backend/app/scheduler/scoring_job.py
from __future__ import annotations
import logging
from datetime import date, datetime, time
from app.scheduler.calendar import TradingCalendar, load_default_calendar

logger = logging.getLogger(__name__)


def run_scoring(eval_date: date | None = None, *, calendar: TradingCalendar | None = None,
                session_factory=None, fetch_confirmed_close=None, fetch_morning_vwap=None,
                overnight_scan=None):
    calendar = calendar or load_default_calendar()
    eval_date = eval_date or datetime.now().date()
    if not calendar.is_trading_day(eval_date):
        logger.info("non-trading day %s, scoring skip", eval_date)
        return None

    run_date = calendar.prev_trading_day(eval_date)     # t→t+1 역매핑

    if session_factory is None:
        from app.store.db import SessionLocal as session_factory
    if fetch_confirmed_close is None:
        from app.data.pykrx_client import fetch_confirmed_close
    if fetch_morning_vwap is None:
        from app.data.kis_client import fetch_morning_vwap
    if overnight_scan is None:
        from app.data.dart_client import overnight_scan

    from app.store.models import Recommendation, Performance
    from sqlalchemy import select

    scored = 0
    with session_factory() as db:
        recs = db.scalars(select(Recommendation).where(Recommendation.run_date == run_date)).all()
        for rec in recs:
            if db.scalar(select(Performance).where(Performance.rec_id == rec.id)):
                continue   # 멱등: 이미 채점됨

            close_t = fetch_confirmed_close(rec.ticker, run_date)     # close[t] (확정)
            if close_t is not None:
                rec.buy_price_final = close_t
            vwap = fetch_morning_vwap(rec.ticker, eval_date)          # VWAP[t+1] 09:00–10:00

            if vwap is None or close_t is None or close_t == 0:
                outcome, ret = "NA", None                            # 잠김/결측 → 분모 제외
            else:
                ret = vwap / close_t - 1.0
                outcome = "SUCCESS" if ret > 0 else "FAIL"

            flag = overnight_scan(rec.ticker,
                                  datetime.combine(run_date, time(15, 20)),
                                  datetime.combine(eval_date, time(9, 0)))
            db.add(Performance(rec_id=rec.id, eval_date=eval_date, buy_price_final=close_t,
                               vwap_0900_1000=vwap, morning_return=ret, outcome=outcome,
                               dart_overnight_flag=flag, scored_at=datetime.now()))
            scored += 1
        db.commit()
    logger.info("scored %d picks for run_date=%s eval_date=%s", scored, run_date, eval_date)
    return scored


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_scoring()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/scheduler/test_scoring_job.py -q
# 기대: 3 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/scheduler/scoring_job.py backend/tests/scheduler/test_scoring_job.py
git commit -m "feat(scheduler): 익일 채점(확정종가·오전VWAP·N/A·DART재스캔·룩어헤드가드·멱등)"
```

---

## Task 11: Windows 작업스케줄러 등록 + MVP 엔지니어링 수용기준 가드

**Files:** Create `backend/scripts/register_tasks.ps1`, `backend/scripts/README_scheduler.md`, `backend/tests/acceptance/test_mvp_gates.py`

3개 잡(premarket 08:30 / daily_run 15:18→15:20 창 / scoring 09:05)을 `Register-ScheduledTask`로 등록한다. 수용기준 가드 테스트로 "보드 완료 정의"(15:20–15:30 창 내·커버리지 바닥·룩어헤드 가드 그린)를 한 스위트에 고정한다.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/acceptance/test_mvp_gates.py
"""MVP 엔지니어링 수용기준 — 보드 '완료' 정의(아키텍처 §5 발행 게이트)."""
from datetime import date, datetime, time
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.store.models import Base, Run, Recommendation
from app.scheduler.calendar import TradingCalendar
from app.scheduler import daily_run, scoring_job

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _cal(early=None):
    return TradingCalendar(holidays={date(2026, 7, 1)}, early_close=early or {})


# 게이트 1: 15:20–15:30 창 내 산출(정규=15:20, 특수=마감−10)
def test_gate_snapshot_within_window():
    cal = _cal(early={date(2026, 9, 29): time(14, 0)})
    snap = cal.snapshot_at(date(2026, 6, 30))
    assert time(15, 20) <= snap.time() < time(15, 30)
    assert cal.snapshot_at(date(2026, 9, 29)) == datetime(2026, 9, 29, 13, 50)


# 게이트 2: 커버리지 바닥(<70%) 미만이면 미발행
def test_gate_coverage_floor_blocks_publish(session_factory):
    rc = daily_run.run_daily(
        date(2026, 6, 30), calendar=_cal(),
        run_pipeline=lambda d, s: SimpleNamespace(
            run_date=d, session_type="정규", data_available=True, kis_coverage_pct=69.9,
            recommendations=[], regimes={}),
        session_factory=session_factory, notify=lambda t, m: None,
        snapshots=SimpleNamespace(write_snapshot=lambda d, p: None))
    assert rc == "UNPUBLISHED"
    with session_factory() as db:
        assert db.get(Run, date(2026, 6, 30)).board_published is False


# 게이트 3: 룩어헤드 가드(채점은 close[t]·VWAP[t+1])
def test_gate_scoring_lookahead_guard(session_factory):
    with session_factory() as db:
        db.add(Recommendation(id=1, run_date=date(2026, 6, 29), ticker="AAA", name="N", market="KOSPI",
                              rank=1, price_provisional=10.0, buy_price_provisional=10.0, buy_price_final=None,
                              s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=1.0,
                              veto=1, core=1.0, final=1.0, grade="S", near_252=1.0, near_60=1.0, rvol=2.0,
                              target_price=11.0, stop_price=9.0, provisional_flag=True, created_at=datetime.now()))
        db.commit()
    seen = {}
    scoring_job.run_scoring(
        date(2026, 6, 30), calendar=_cal(), session_factory=session_factory,
        fetch_confirmed_close=lambda t, d: seen.__setitem__("close", d) or 10.0,
        fetch_morning_vwap=lambda t, d: seen.__setitem__("vwap", d) or 10.5,
        overnight_scan=lambda t, s, u: False)
    assert seen["close"] == date(2026, 6, 29)   # t
    assert seen["vwap"] == date(2026, 6, 30)    # t+1 (미래 정보로 진입가 산정 안 함)


# 게이트 4: Windows 등록 스크립트가 3개 잡을 정의
def test_register_script_defines_three_jobs():
    text = (SCRIPTS / "register_tasks.ps1").read_text(encoding="utf-8")
    assert "app.scheduler.premarket" in text
    assert "app.scheduler.daily_run" in text
    assert "app.scheduler.scoring_job" in text
    assert "15:18" in text or "15:20" in text
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/acceptance/test_mvp_gates.py -q
# 기대: FileNotFoundError(register_tasks.ps1) + 일부 통과 → 1 failed (게이트4)
```

- [ ] **Step 3: 최소 구현**

```powershell
# backend/scripts/register_tasks.ps1
# 종가베팅 추천 시스템 — Windows 작업스케줄러 3잡 등록
# 사용: 관리자 PowerShell에서  .\register_tasks.ps1 -PythonExe "C:\Python314\python.exe" -BackendDir "D:\work\git\closing-bet-recommender\backend"
param(
    [string]$PythonExe = "python",
    [string]$BackendDir = "$PSScriptRoot\.."
)

$BackendDir = (Resolve-Path $BackendDir).Path

function Register-OneTask {
    param([string]$Name, [string]$Module, [string]$Time)
    $action  = New-ScheduledTaskAction -Execute $PythonExe -Argument "-m $Module" -WorkingDirectory $BackendDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "registered: $Name -> -m $Module @ $Time"
}

# 장전 FINAL prefetch + 헬스체크 (fail-closed)
Register-OneTask -Name "CBR-Premarket" -Module "app.scheduler.premarket" -Time "08:30"
# 15:20 런 — 15:18 기동(부팅·토큰 갱신 여유), 모듈이 캘린더로 15:20–15:30 창·거래일 판정
Register-OneTask -Name "CBR-DailyRun"  -Module "app.scheduler.daily_run" -Time "15:18"
# 익일 오전 채점(09:00–10:00 VWAP 산출 후) + DART 오버나잇 재스캔
Register-OneTask -Name "CBR-Scoring"   -Module "app.scheduler.scoring_job" -Time "09:05"

Write-Host "done. 확인: Get-ScheduledTask -TaskName 'CBR-*'"
```
```markdown
<!-- backend/scripts/README_scheduler.md -->
# Windows 작업스케줄러 운영

## 등록
관리자 PowerShell:
```
.\scripts\register_tasks.ps1 -PythonExe "C:\Python314\python.exe" -BackendDir "D:\work\git\closing-bet-recommender\backend"
```

## 3개 잡
| 잡 | 모듈 | 시각 | 책임 |
|---|---|---|---|
| CBR-Premarket | `python -m app.scheduler.premarket` | 08:30 | FINAL prefetch + 헬스체크(실패→fail-closed) |
| CBR-DailyRun  | `python -m app.scheduler.daily_run` | 15:18 | 거래일·세션 판정 후 15:20 스냅샷 파이프라인, 커버리지<70%→미발행, top3 알림 |
| CBR-Scoring   | `python -m app.scheduler.scoring_job` | 09:05 | 전 거래일 픽 채점(확정종가·오전VWAP·N/A) + DART 오버나잇 재스캔 |

## 운영 메모
- 각 모듈은 `TradingCalendar`로 거래일/특수세션을 자체 판정 → 휴장일엔 즉시 종료.
- 특수세션(조기폐장)은 캘린더 마감−10분으로 스냅샷 자동 시프트.
- PC 절전/네트워크 끊김 시 그날 추천 없음(미스). `-WakeToRun`으로 절전 복귀 시도.
- 발행 게이트(보드 '완료'): ① 15:20–15:30 창 내 ② 커버리지≥70% ③ 룩어헤드/풀-재현 가드 그린.
- 해제: `Unregister-ScheduledTask -TaskName 'CBR-Premarket','CBR-DailyRun','CBR-Scoring' -Confirm:$false`
```

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/acceptance/test_mvp_gates.py -q
# 기대: 4 passed
# 전체 회귀:
python -m pytest tests/ -q
# 기대: 모든 테스트 passed (api + scheduler + acceptance)
```

- [ ] **Step 5: 커밋**

```
git add backend/scripts/register_tasks.ps1 backend/scripts/README_scheduler.md backend/tests/acceptance/test_mvp_gates.py
git commit -m "feat(deploy): Windows 작업스케줄러 3잡 등록 + MVP 수용기준 가드(창·커버리지·룩어헤드)"
```

---

## 완료 정의 (이 서브시스템)

- [ ] `python -m pytest tests/ -q` 전부 그린 (api 6엔드포인트 + 스케줄러 4잡 + 수용기준).
- [ ] `/recommendations`·`/stock`·`/performance`·`/universe`·`/backtest`·`/health` 응답 스키마(pydantic) 고정, `main.create_app()`에 전부 등록.
- [ ] 캘린더: 휴장·조기폐장(마감−10)·수능지연(15:30 유지)·t→t+1 매핑 테스트 통과.
- [ ] premarket fail-closed(BLOCKED·prefetch 미실행), daily_run 커버리지<70% & KIS 전면불가 미발행, scoring N/A·멱등·룩어헤드 가드 테스트 통과.
- [ ] Windows 작업스케줄러 등록 스크립트/문서 제공, 3잡 모듈 엔트리포인트(`python -m app.scheduler.*`) 동작.

> 의존 주의: 본 플랜은 서브시스템 1(`store/db.py`·`store/models.py`·`store/snapshots.py`·`data/*`)과 2(`engine/pipeline.py`)가 위 "의존 인터페이스 계약"대로 존재해야 실행된다. `/backtest`만 서브시스템 3(`backtest/engine.py`)에 의존하며 그 외 엔드포인트/잡은 1·2만으로 충분하다. 모든 외부 API는 주입 경계 뒤이므로 테스트는 네트워크 호출 없이 목으로만 동작한다.

---

작성한 플랜은 위 본문이 전부입니다. 관련 입력 파일(절대경로): 스펙 `D:\work\git\closing-bet-recommender\docs\superpowers\specs\2026-06-30-closing-bet-recommender-design.md`, 아키텍처 `D:\work\git\closing-bet-recommender\docs\superpowers\specs\2026-06-30-architecture.md`.
