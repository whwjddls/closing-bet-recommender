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

**Files:** Create `backend/app/main.py`, `backend/app/api/__init__.py`, `backend/app/api/schemas.py`, `backend/app/api/health.py`; Test `backend/tests/api/conftest.py`, `backend/tests/api/test_health.py`

`create_app()` 팩토리로 라우터를 등록하고 CORS(Vite dev 5173)를 연다. `/health`는 최신 `Run`과 `universe_cache.as_of`로 데이터 신선도/발행상태를 반환한다.

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
from app.store.models import Run, UniverseCache


def test_health_down_when_no_runs(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "down"
    assert body["last_run_date"] is None


def test_health_ok_when_latest_run_published(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime(2026, 6, 30, 15, 20),
                       finished_at=datetime(2026, 6, 30, 15, 20, 14), status="OK",
                       kis_coverage_pct=92.0, board_published=True, session_type="정규", reason=None))
    db_session.add(UniverseCache(ticker="000660", name="SK하이닉스", market="KOSPI", sec_type="보통주",
                                 avg_value_20d=5e11, is_managed=False, is_warning=False, is_caution=False,
                                 listing_days=4000, eligible=True, as_of=date(2026, 6, 30)))
    db_session.commit()
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["last_run_date"] == "2026-06-30"
    assert body["kis_coverage_pct"] == 92.0
    assert body["universe_as_of"] == "2026-06-30"


def test_health_degraded_when_unpublished(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 29), started_at=datetime(2026, 6, 29, 15, 20),
                       finished_at=datetime(2026, 6, 29, 15, 20, 5), status="UNPUBLISHED",
                       kis_coverage_pct=61.0, board_published=False, session_type="정규",
                       reason="커버리지 61% < 70%"))
    db_session.commit()
    body = client.get("/health").json()
    assert body["status"] == "degraded"
    assert "커버리지" in body["detail"]
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
# backend/app/api/schemas.py
from __future__ import annotations
from datetime import date
from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    status: str                         # ok | degraded | down
    last_run_date: date | None = None
    last_run_status: str | None = None
    board_published: bool | None = None
    kis_coverage_pct: float | None = None
    universe_as_of: date | None = None
    detail: str
```
```python
# backend/app/api/health.py
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Run, UniverseCache
from app.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(db: Session = Depends(get_db)) -> HealthResponse:
    last_run = db.scalars(select(Run).order_by(Run.run_date.desc()).limit(1)).first()
    universe_as_of = db.scalars(
        select(UniverseCache.as_of).order_by(UniverseCache.as_of.desc()).limit(1)
    ).first()

    if last_run is None:
        status, detail = "down", "런 기록 없음"
    elif last_run.status == "OK" and last_run.board_published:
        status, detail = "ok", "정상"
    else:
        status, detail = "degraded", (last_run.reason or last_run.status)

    return HealthResponse(
        status=status,
        last_run_date=last_run.run_date if last_run else None,
        last_run_status=last_run.status if last_run else None,
        board_published=last_run.board_published if last_run else None,
        kis_coverage_pct=last_run.kis_coverage_pct if last_run else None,
        universe_as_of=universe_as_of,
        detail=detail,
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
git commit -m "feat(api): FastAPI 앱 팩토리 + GET /health(런·유니버스 신선도)"
```

---

## Task 3: `GET /recommendations/{run_date}` (`api/recommendations.py`)

**Files:** Modify `backend/app/api/schemas.py`, `backend/app/main.py`; Create `backend/app/api/recommendations.py`; Test `backend/tests/api/test_recommendations.py`

추천 보드 + 레짐 게이지를 반환한다. 등급=`core` 기준(이미 저장된 값). 빈/저레짐 배너: 전 레짐 0.0 → "오늘은 시황 레짐상 추천 없음", 0.5 포함 → "반-리스크 레짐(0.5x)". 미발행 Run이면 사유 배너. 정렬은 `rank` 오름차순(동점 tie-break=D-1 거래대금은 엔진이 rank로 확정).

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
                target_price=25200.0, stop_price=23800.0, provisional_flag=True, created_at=datetime.now())
    base.update(kw)
    return Recommendation(**base)


def _published_run(d=date(2026, 6, 30)):
    return Run(run_date=d, started_at=datetime.now(), finished_at=datetime.now(), status="OK",
               kis_coverage_pct=90.0, board_published=True, session_type="정규", reason=None)


def test_recommendations_returns_ranked_rows_and_regime(client, db_session):
    db_session.add(_published_run())
    db_session.add(_rec(rank=2, ticker="005930", name="삼성전자", core=0.55, final=0.55, grade="B"))
    db_session.add(_rec(rank=1))
    db_session.add(RegimeSnapshot(run_date=date(2026, 6, 30), market="KOSPI", index_level=2700.0,
                                  ma5=2680.0, ma5_prev=2670.0, cond_a=True, cond_b=True, regime_mult=1.0))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["board_published"] is True
    assert [r["rank"] for r in body["recommendations"]] == [1, 2]   # rank 오름차순
    assert body["recommendations"][0]["grade"] == "S"
    assert body["recommendations"][0]["exit_rule"].startswith("익일 오전 VWAP")
    assert body["regimes"][0]["regime_mult"] == 1.0
    assert body["banner"] is None


def test_recommendations_empty_board_risk_off_banner(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime.now(), finished_at=datetime.now(),
                       status="OK", kis_coverage_pct=88.0, board_published=True, session_type="정규", reason=None))
    db_session.add(RegimeSnapshot(run_date=date(2026, 6, 30), market="KOSPI", index_level=2600.0,
                                  ma5=2650.0, ma5_prev=2660.0, cond_a=False, cond_b=False, regime_mult=0.0))
    db_session.add(RegimeSnapshot(run_date=date(2026, 6, 30), market="KOSDAQ", index_level=830.0,
                                  ma5=850.0, ma5_prev=860.0, cond_a=False, cond_b=False, regime_mult=0.0))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["recommendations"] == []
    assert "시황 레짐상 추천 없음" in body["banner"]


def test_recommendations_half_risk_banner(client, db_session):
    db_session.add(_published_run())
    db_session.add(_rec())
    db_session.add(RegimeSnapshot(run_date=date(2026, 6, 30), market="KOSPI", index_level=2700.0,
                                  ma5=2680.0, ma5_prev=2690.0, cond_a=True, cond_b=False, regime_mult=0.5))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert "반-리스크 레짐(0.5x)" in body["banner"]


def test_recommendations_unpublished_run_shows_reason_banner(client, db_session):
    db_session.add(Run(run_date=date(2026, 6, 30), started_at=datetime.now(), finished_at=datetime.now(),
                       status="UNPUBLISHED", kis_coverage_pct=61.0, board_published=False,
                       session_type="정규", reason="커버리지 61% < 70%"))
    db_session.commit()
    body = client.get("/recommendations/2026-06-30").json()
    assert body["board_published"] is False
    assert "커버리지" in body["banner"]
    assert body["recommendations"] == []
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_recommendations.py -q
# 기대: 404 또는 ImportError → 4 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py`에 추가:

```python
# backend/app/api/schemas.py  (추가)
EXIT_RULE = "익일 오전 VWAP(09:00–10:00) 매도"


class RecommendationRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rank: int
    ticker: str
    name: str
    market: str
    price_provisional: float
    buy_price_provisional: float
    buy_price_final: float | None = None
    s_shin: float
    s_geo: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    core: float
    final: float
    grade: str
    near_252: float | None = None
    near_60: float | None = None
    rvol: float | None = None
    target_price: float | None = None
    stop_price: float | None = None
    provisional_flag: bool
    exit_rule: str = EXIT_RULE


class RegimeGauge(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    market: str
    index_level: float
    ma5: float
    cond_a: bool
    cond_b: bool
    regime_mult: float


class RecommendationsResponse(BaseModel):
    run_date: date
    session_type: str | None = None
    board_published: bool = False
    status: str
    coverage_pct: float | None = None
    banner: str | None = None
    regimes: list[RegimeGauge] = []
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
from app.api.schemas import RecommendationsResponse, RecommendationRow, RegimeGauge

router = APIRouter(tags=["recommendations"])


def _banner(run: Run | None, regimes: list[RegimeSnapshot], recs: list[Recommendation]) -> str | None:
    if run is None:
        return "해당 일자 추천 없음"
    if not run.board_published:
        return f"미발행: {run.reason or run.status}"
    if regimes and all(rg.regime_mult == 0.0 for rg in regimes):
        return "오늘은 시황 레짐상 추천 없음"
    if any(rg.regime_mult == 0.5 for rg in regimes):
        return "반-리스크 레짐(0.5x)"
    return None


@router.get("/recommendations/{run_date}", response_model=RecommendationsResponse)
def get_recommendations(run_date: date, db: Session = Depends(get_db)) -> RecommendationsResponse:
    run = db.get(Run, run_date)
    recs = db.scalars(
        select(Recommendation).where(Recommendation.run_date == run_date).order_by(Recommendation.rank)
    ).all()
    regimes = db.scalars(
        select(RegimeSnapshot).where(RegimeSnapshot.run_date == run_date)
    ).all()
    return RecommendationsResponse(
        run_date=run_date,
        session_type=run.session_type if run else None,
        board_published=run.board_published if run else False,
        status=run.status if run else "UNKNOWN",
        coverage_pct=run.kis_coverage_pct if run else None,
        banner=_banner(run, list(regimes), list(recs)),
        regimes=[RegimeGauge.model_validate(rg) for rg in regimes],
        recommendations=[RecommendationRow.model_validate(r) for r in recs],
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
git commit -m "feat(api): GET /recommendations/{date} 보드+레짐+빈/저레짐 배너"
```

---

## Task 4: `GET /stock/{code}` (`api/stock.py`)

**Files:** Modify `backend/app/api/schemas.py`, `backend/app/main.py`; Create `backend/app/api/stock.py`; Test `backend/tests/api/test_stock.py`

종목 상세 = 신호 기여도(s_신/rvol_confirm/supply_tilt/regime/veto/core/final + near/rvol). 기본은 해당 종목의 **최신 run_date** 추천, `?date=`로 특정일 조회. 미존재 시 404.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_stock.py
from datetime import date, datetime
from app.store.models import Recommendation


def _rec(d, **kw):
    base = dict(run_date=d, ticker="000660", name="SK하이닉스", market="KOSPI", rank=1,
                price_provisional=24500.0, buy_price_provisional=24500.0, buy_price_final=None,
                s_shin=1.16, s_geo=0.83, rvol_confirm=0.93, supply_tilt=1.03, regime_mult=1.0, veto=1,
                core=1.12, final=1.12, grade="S", near_252=1.02, near_60=1.04, rvol=2.5,
                target_price=25200.0, stop_price=23800.0, provisional_flag=True, created_at=datetime.now())
    base.update(kw)
    return Recommendation(**base)


def test_stock_returns_latest_run_signal_contribution(client, db_session):
    db_session.add(_rec(date(2026, 6, 29), core=0.7, final=0.7, grade="A"))
    db_session.add(_rec(date(2026, 6, 30), core=1.12, final=1.12, grade="S"))
    db_session.commit()
    body = client.get("/stock/000660").json()
    assert body["run_date"] == "2026-06-30"            # 최신
    assert body["grade"] == "S"
    assert body["s_shin"] == 1.16
    assert body["rvol_confirm"] == 0.93
    assert body["regime_mult"] == 1.0
    assert body["core"] == 1.12


def test_stock_specific_date_query(client, db_session):
    db_session.add(_rec(date(2026, 6, 29), core=0.7, final=0.7, grade="A"))
    db_session.add(_rec(date(2026, 6, 30)))
    db_session.commit()
    body = client.get("/stock/000660?on=2026-06-29").json()
    assert body["run_date"] == "2026-06-29"
    assert body["grade"] == "A"


def test_stock_404_when_missing(client):
    assert client.get("/stock/999999").status_code == 404
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_stock.py -q
# 기대: 404 미스매치/ImportError → 3 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py`에 추가:

```python
# backend/app/api/schemas.py  (추가)
class StockDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    run_date: date
    ticker: str
    name: str
    market: str
    price_provisional: float
    buy_price_provisional: float
    buy_price_final: float | None = None
    target_price: float | None = None
    stop_price: float | None = None
    grade: str
    core: float
    final: float
    s_shin: float
    s_geo: float
    rvol_confirm: float
    supply_tilt: float
    regime_mult: float
    veto: int
    near_252: float | None = None
    near_60: float | None = None
    rvol: float | None = None
    provisional_flag: bool
    exit_rule: str = EXIT_RULE
```
```python
# backend/app/api/stock.py
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Recommendation
from app.api.schemas import StockDetailResponse

router = APIRouter(tags=["stock"])


@router.get("/stock/{code}", response_model=StockDetailResponse)
def get_stock(code: str, on: date | None = None, db: Session = Depends(get_db)) -> StockDetailResponse:
    stmt = select(Recommendation).where(Recommendation.ticker == code)
    if on is not None:
        stmt = stmt.where(Recommendation.run_date == on)
    stmt = stmt.order_by(Recommendation.run_date.desc()).limit(1)
    rec = db.scalars(stmt).first()
    if rec is None:
        raise HTTPException(status_code=404, detail=f"종목 {code} 추천 이력 없음")
    return StockDetailResponse.model_validate(rec)
```

`main.py`에 `from app.api import ..., stock` 추가 + `app.include_router(stock.router)`.

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_stock.py -q
# 기대: 3 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/schemas.py backend/app/api/stock.py backend/app/main.py backend/tests/api/test_stock.py
git commit -m "feat(api): GET /stock/{code} 신호 기여도 상세(최신/특정일)"
```

---

## Task 5: `GET /performance` (`api/performance.py`)

**Files:** Modify `backend/app/api/schemas.py`, `backend/app/main.py`; Create `backend/app/api/performance.py`; Test `backend/tests/api/test_performance.py`

종목별 결과 테이블 + 집계. **N/A는 분모 제외**(적중률 = SUCCESS/(SUCCESS+FAIL)). 등급별·레짐별 적중률. 콜드스타트: 누적 추천 < 30이면 `cold_start=True`.

- [ ] **Step 1: 실패 테스트 작성**

```python
# backend/tests/api/test_performance.py
from datetime import date, datetime
from app.store.models import Recommendation, Performance


def _rec(rid, grade="S", regime=1.0, ticker="000660"):
    return Recommendation(id=rid, run_date=date(2026, 6, 29), ticker=ticker, name="N", market="KOSPI",
                          rank=rid, price_provisional=1.0, buy_price_provisional=1.0, buy_price_final=None,
                          s_shin=1.0, s_geo=0.5, rvol_confirm=0.9, supply_tilt=1.0, regime_mult=regime,
                          veto=1, core=1.0, final=1.0, grade=grade, near_252=1.0, near_60=1.0, rvol=2.0,
                          target_price=1.1, stop_price=0.9, provisional_flag=True, created_at=datetime.now())


def _perf(rid, outcome, ret, vwap=10.0, flag=False):
    return Performance(rec_id=rid, eval_date=date(2026, 6, 30), buy_price_final=10.0,
                       vwap_0900_1000=vwap, morning_return=ret, outcome=outcome,
                       dart_overnight_flag=flag, scored_at=datetime.now())


def test_performance_excludes_na_from_hit_rate(client, db_session):
    db_session.add_all([_rec(1, "S", 1.0, "000660"), _rec(2, "A", 1.0, "005930"), _rec(3, "B", 0.5, "035720")])
    db_session.add_all([
        _perf(1, "SUCCESS", 0.0053, vwap=10.6),
        _perf(2, "FAIL", -0.004, vwap=9.96),
        _perf(3, "NA", None, vwap=None, flag=True),   # 잠김 → 분모 제외
    ])
    db_session.commit()
    body = client.get("/performance").json()
    agg = body["aggregate"]
    assert agg["total_scored"] == 2                # NA 제외
    assert agg["success_count"] == 1
    assert abs(agg["hit_rate"] - 0.5) < 1e-9
    assert agg["cold_start"] is True               # 누적 픽 3 < 30
    assert agg["by_grade"]["S"] == 1.0
    assert agg["by_regime"]["0.5"] == 0.0 or "0.5" not in agg["by_regime"]  # NA뿐인 레짐은 분모0→제외
    rows = {r["ticker"]: r for r in body["rows"]}
    assert rows["035720"]["outcome"] == "NA"
    assert rows["035720"]["dart_overnight_flag"] is True


def test_performance_empty(client):
    body = client.get("/performance").json()
    assert body["aggregate"]["hit_rate"] is None
    assert body["aggregate"]["cold_start"] is True
    assert body["rows"] == []
```

- [ ] **Step 2: 실패 확인**

```
python -m pytest tests/api/test_performance.py -q
# 기대: ImportError/404 → 2 failed/errors
```

- [ ] **Step 3: 최소 구현**

`schemas.py`에 추가:

```python
# backend/app/api/schemas.py  (추가)
class PerformanceRow(BaseModel):
    ticker: str
    name: str
    grade: str
    eval_date: date
    buy_price_final: float | None = None
    vwap_0900_1000: float | None = None
    morning_return: float | None = None
    outcome: str
    dart_overnight_flag: bool


class PerformanceAggregate(BaseModel):
    total_scored: int                  # SUCCESS + FAIL (NA 제외)
    success_count: int
    hit_rate: float | None = None
    avg_morning_return: float | None = None
    cold_start: bool
    by_grade: dict[str, float] = {}
    by_regime: dict[str, float] = {}


class PerformanceResponse(BaseModel):
    aggregate: PerformanceAggregate
    rows: list[PerformanceRow] = []
```
```python
# backend/app/api/performance.py
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.store.db import get_db
from app.store.models import Recommendation, Performance
from app.api.schemas import PerformanceResponse, PerformanceRow, PerformanceAggregate

router = APIRouter(tags=["performance"])
COLD_START_MIN = 30


def _hit_rate(success: int, fail: int) -> float | None:
    denom = success + fail
    return success / denom if denom else None


@router.get("/performance", response_model=PerformanceResponse)
def get_performance(db: Session = Depends(get_db)) -> PerformanceResponse:
    pairs = db.execute(
        select(Performance, Recommendation).join(Recommendation, Performance.rec_id == Recommendation.id)
        .order_by(Performance.eval_date.desc(), Recommendation.rank)
    ).all()

    rows: list[PerformanceRow] = []
    success = fail = 0
    ret_sum = 0.0
    by_grade: dict[str, list[int]] = {}     # grade -> [success, fail]
    by_regime: dict[str, list[int]] = {}    # regime_mult(str) -> [success, fail]

    for perf, rec in pairs:
        rows.append(PerformanceRow(
            ticker=rec.ticker, name=rec.name, grade=rec.grade, eval_date=perf.eval_date,
            buy_price_final=perf.buy_price_final, vwap_0900_1000=perf.vwap_0900_1000,
            morning_return=perf.morning_return, outcome=perf.outcome,
            dart_overnight_flag=perf.dart_overnight_flag,
        ))
        if perf.outcome == "NA":
            continue
        is_ok = perf.outcome == "SUCCESS"
        success += int(is_ok)
        fail += int(not is_ok)
        if perf.morning_return is not None:
            ret_sum += perf.morning_return
        by_grade.setdefault(rec.grade, [0, 0])[0 if is_ok else 1] += 1
        by_regime.setdefault(f"{rec.regime_mult}", [0, 0])[0 if is_ok else 1] += 1

    total = success + fail
    total_recs = db.scalar(select(func.count()).select_from(Recommendation)) or 0
    aggregate = PerformanceAggregate(
        total_scored=total,
        success_count=success,
        hit_rate=_hit_rate(success, fail),
        avg_morning_return=(ret_sum / total) if total else None,
        cold_start=total_recs < COLD_START_MIN,
        by_grade={g: _hit_rate(s, f) for g, (s, f) in by_grade.items() if (s + f)},
        by_regime={r: _hit_rate(s, f) for r, (s, f) in by_regime.items() if (s + f)},
    )
    return PerformanceResponse(aggregate=aggregate, rows=rows)
```

`main.py`에 `performance` 라우터 등록.

- [ ] **Step 4: 통과 확인**

```
python -m pytest tests/api/test_performance.py -q
# 기대: 2 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/api/schemas.py backend/app/api/performance.py backend/app/main.py backend/tests/api/test_performance.py
git commit -m "feat(api): GET /performance 종목별 결과+집계(N/A 분모제외·콜드스타트)"
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
# 기대: AttributeError: module 'app.scheduler.premarket' has no attribute 'run_premarket' → 3 failed/errors
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
    report = health_check()
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
# 기대: 3 passed
```

- [ ] **Step 5: 커밋**

```
git add backend/app/scheduler/premarket.py backend/tests/scheduler/test_premarket.py
git commit -m "feat(scheduler): 장전 prefetch + 헬스체크 fail-closed(BLOCKED·알림)"
```

---

## Task 9: 15:20 런 스케줄러 — `scheduler/daily_run.py` (커버리지 게이트·top3 알림)

**Files:** Create `backend/app/scheduler/daily_run.py`; Test `backend/tests/scheduler/test_daily_run.py`

`run_pipeline(run_date, snapshot_at)` 호출 → `data_available=False` 또는 `kis_coverage_pct<70` → **미발행(UNPUBLISHED)**, 아니면 추천/레짐 영속화 + JSON 스냅샷 + `runs.status=OK` + top3 알림. 스냅샷 시각은 캘린더(특수세션=마감−10).

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
