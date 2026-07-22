"""수동 실행 트리거 — UI 버튼용 ``POST /run`` + ``GET /run/status``.

``run_daily()`` 를 데몬 백그라운드 스레드에서 1회 실행한다. 동시 2회 실행은
모듈 레벨 락으로 차단(``already_running``). 스레드 본문은 try/except 로 감싸
결과/에러를 모듈 상태에 저장한다(널-안전).
"""
from __future__ import annotations

import threading
from datetime import date, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import (
    PrefetchTodayResponse,
    RunStatusResponse,
    RunTodayResponse,
    RunTriggerResponse,
)
from app.store.db import get_db
from app.store.models import FinalPrefetch, Recommendation, Run, UniverseCache

router = APIRouter(tags=["run"])

_lock = threading.Lock()
_state: dict = {
    "running": False,
    "last_result": None,
    "last_error": None,
    "finished_at": None,
    "started_at": None,        # ISO — 경과 표시용
    "started_ts": None,        # epoch — elapsed 계산용
}


def _invoke_run_daily():
    """프로덕션 seam — 라이브 스케줄러 런. 테스트는 이 심볼을 monkeypatch."""
    from app.scheduler.daily_run import run_daily

    return run_daily()


def _execute() -> None:
    try:
        result = _invoke_run_daily()
        # 비거래일(None) → "SKIPPED", 그 외는 "OK"/"UNPUBLISHED" 등 문자열 그대로.
        _state["last_result"] = "SKIPPED" if result is None else str(result)
        _state["last_error"] = None
    except Exception as exc:                       # noqa: BLE001  (백그라운드 런 방어)
        _state["last_result"] = None
        _state["last_error"] = str(exc)
    finally:
        _state["finished_at"] = datetime.now().isoformat()
        with _lock:
            _state["running"] = False


@router.post("/run", response_model=RunTriggerResponse)
def trigger_run() -> RunTriggerResponse:
    with _lock:
        if _state["running"]:
            return RunTriggerResponse(status="already_running")
        _state["running"] = True
        _state["last_error"] = None
        now = datetime.now()
        _state["started_at"] = now.isoformat()
        _state["started_ts"] = now.timestamp()
    thread = threading.Thread(target=_execute, daemon=True)
    thread.start()
    return RunTriggerResponse(status="started")


@router.get("/run/today", response_model=RunTodayResponse)
def get_run_today(db: Session = Depends(get_db)) -> RunTodayResponse:
    """오늘 런 기록(DB) — 작업스케줄러가 별도 프로세스로 돌린 런도 보인다."""
    run = db.get(Run, date.today())
    if run is None:
        return RunTodayResponse(ran=False)
    count = db.scalar(select(func.count()).select_from(Recommendation)
                      .where(Recommendation.run_date == run.run_date)) or 0
    return RunTodayResponse(
        ran=True, status=run.status, board_published=bool(run.board_published),
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        reason=run.reason, published_count=count, funnel=run.funnel)


@router.get("/prefetch/today", response_model=PrefetchTodayResponse)
def get_prefetch_today(db: Session = Depends(get_db)) -> PrefetchTodayResponse:
    """오늘 프리스캔(장전 프리페치) 산출물 유무 — DB 기반이라 08:30 스케줄러가 별도
    프로세스로 돌린 실행도 그대로 보인다(``/jobs/prefetch/status`` 는 웹서버 프로세스
    내부 상태라 스케줄러 실행을 못 본다). UI 헤더가 '했는지/안 했는지'를 이걸로 판단한다."""
    today = date.today()
    tickers = db.scalar(select(func.count()).select_from(FinalPrefetch)
                        .where(FinalPrefetch.run_date == today)) or 0
    universe = db.scalar(select(func.count()).select_from(UniverseCache)
                         .where(UniverseCache.as_of == today)) or 0
    if tickers == 0 and universe == 0:
        return PrefetchTodayResponse(ran=False)
    return PrefetchTodayResponse(ran=True, ticker_count=tickers,
                                 universe_count=universe, as_of=today.isoformat())


@router.get("/run/status", response_model=RunStatusResponse)
def get_run_status() -> RunStatusResponse:
    elapsed = None
    if _state["running"] and _state.get("started_ts"):
        elapsed = round(datetime.now().timestamp() - _state["started_ts"], 1)
    return RunStatusResponse(
        running=bool(_state["running"]),
        last_result=_state["last_result"],
        last_error=_state["last_error"],
        finished_at=_state["finished_at"],
        started_at=_state.get("started_at"),
        elapsed_sec=elapsed,
    )
