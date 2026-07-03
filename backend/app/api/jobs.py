"""수동 잡 트리거 — UI 버튼용 ``POST /jobs/{prefetch|scoring}`` + 상태 조회.

run.py(스캔 버튼)와 동일한 계약: 잡을 데몬 백그라운드 스레드에서 1회 실행하고,
동시 2회 실행은 잡별 모듈 락으로 차단(``already_running``), 상태는
``RunStatusResponse`` 형태로 3초 폴링한다.

- prefetch(종목 후보 가져오기): 장전 프리페치. 언제 돌려도 안전(D-1 확정 데이터만 사용).
- scoring(성과 채점): **오전 10시 이전 트리거는 거부(rejected)** — 09:00–10:00
  VWAP 창이 끝나기 전에 돌리면 부분 VWAP으로 오채점되고 멱등 가드 때문에
  영구 고착된다(작업 스케줄러 09:05 버그와 동일 뿌리).
"""
from __future__ import annotations

import threading
from datetime import datetime, time

from fastapi import APIRouter

from app.api.schemas import JobTriggerResponse, RunStatusResponse

router = APIRouter(tags=["jobs"])

SCORING_EARLIEST = time(10, 0)   # 09:00–10:00 VWAP 창 완료 후에만 채점 허용
SCORING_TOO_EARLY_REASON = (
    "오전 10시 이후에 눌러주세요 — 9~10시 아침 평균가 집계가 끝나야 채점할 수 있어요"
)


def _invoke_prefetch():
    """프로덕션 seam — 장전 프리페치(종목 후보 가져오기). 테스트는 monkeypatch."""
    from app.scheduler.premarket import run_premarket

    return run_premarket()


def _invoke_scoring():
    """프로덕션 seam — 전 거래일 픽 채점. 테스트는 monkeypatch."""
    from app.scheduler.scoring_job import run_scoring

    return run_scoring()


def _now() -> datetime:
    """시각 seam(채점 10시 가드) — 테스트는 monkeypatch."""
    return datetime.now()


def _new_state() -> dict:
    return {"running": False, "last_result": None, "last_error": None,
            "finished_at": None, "started_at": None, "started_ts": None}


_locks: dict[str, threading.Lock] = {
    "prefetch": threading.Lock(),
    "scoring": threading.Lock(),
}
_states: dict[str, dict] = {"prefetch": _new_state(), "scoring": _new_state()}


def _result_label(job: str, result) -> str:
    if result is None:
        return "SKIPPED"                     # 비거래일/휴장 — 잡이 스스로 스킵
    if job == "scoring":
        return f"SCORED:{int(result)}"       # 채점 건수(0=채점할 픽 없음)
    return str(result)


def _execute(job: str, invoke) -> None:
    state = _states[job]
    try:
        state["last_result"] = _result_label(job, invoke())
        state["last_error"] = None
    except Exception as exc:                  # noqa: BLE001  (백그라운드 런 방어)
        state["last_result"] = None
        state["last_error"] = str(exc)
    finally:
        state["finished_at"] = datetime.now().isoformat()
        with _locks[job]:
            state["running"] = False


def _trigger(job: str, invoke) -> JobTriggerResponse:
    state = _states[job]
    with _locks[job]:
        if state["running"]:
            return JobTriggerResponse(status="already_running")
        state["running"] = True
        state["last_error"] = None
        now = datetime.now()
        state["started_at"] = now.isoformat()
        state["started_ts"] = now.timestamp()
    threading.Thread(target=_execute, args=(job, invoke), daemon=True).start()
    return JobTriggerResponse(status="started")


def _status(job: str) -> RunStatusResponse:
    state = _states[job]
    elapsed = None
    if state["running"] and state.get("started_ts"):
        elapsed = round(datetime.now().timestamp() - state["started_ts"], 1)
    return RunStatusResponse(
        running=bool(state["running"]),
        last_result=state["last_result"],
        last_error=state["last_error"],
        finished_at=state["finished_at"],
        started_at=state.get("started_at"),
        elapsed_sec=elapsed,
    )


@router.post("/jobs/prefetch", response_model=JobTriggerResponse)
def trigger_prefetch() -> JobTriggerResponse:
    return _trigger("prefetch", _invoke_prefetch)


@router.get("/jobs/prefetch/status", response_model=RunStatusResponse)
def prefetch_status() -> RunStatusResponse:
    return _status("prefetch")


@router.post("/jobs/scoring", response_model=JobTriggerResponse)
def trigger_scoring() -> JobTriggerResponse:
    if _now().time() < SCORING_EARLIEST:
        return JobTriggerResponse(status="rejected", reason=SCORING_TOO_EARLY_REASON)
    return _trigger("scoring", _invoke_scoring)


@router.get("/jobs/scoring/status", response_model=RunStatusResponse)
def scoring_status() -> RunStatusResponse:
    return _status("scoring")
