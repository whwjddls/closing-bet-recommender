"""EXE 내장 스케줄러 — Windows 작업스케줄러 대체 (프로세스 상주형).

APScheduler 로 3잡을 시각에만 건다. **거래일 판정·발행 창·룩어헤드 가드는 각 잡
모듈이 스스로 수행한다** — 여기서 중복 판정하면 진실이 두 곳에 생긴다.

  08:30 premarket   헬스체크 + corp_code_map 시딩 + FINAL 프리페치
  15:18 daily_run   15:20 스냅샷 스캔 → 발행 → 텔레그램 (모듈이 15:15–15:30 창 재검증)
  10:05 scoring     전 거래일 픽 채점 (09:00–10:00 VWAP 창 완료 후여야 함)

잡 예외는 삼킨다 — 하루치 실패로 스케줄러 스레드가 죽으면 남은 잡이 전부 유실된다.
콜라보레이터는 모두 주입(테스트는 네트워크·시계 없이 동작).

한계(설계상 수용): 프로세스가 떠 있어야 돈다. Windows 작업스케줄러와 달리 절전에서
PC를 깨우지 못한다. 그래서 EXE 를 부팅 시 자동 실행하고 트레이에 상주시킨다.
"""
from __future__ import annotations

import logging
from typing import Callable

from app.scheduler.calendar import load_default_calendar

logger = logging.getLogger(__name__)

# 작업스케줄러(register_tasks.ps1)와 동일한 시각 — 두 방식의 동작을 일치시킨다.
PREMARKET_AT = (8, 30)
DAILY_RUN_AT = (15, 18)     # 15:20 스냅샷 직전 기동(부팅·토큰 갱신 여유)
SCORING_AT = (10, 5)        # 09:00–10:00 VWAP 창 완료 후 (10시 이전 금지)

JOB_IDS = ("premarket", "daily_run", "scoring")


def _invoke_premarket():
    from app.scheduler.premarket import run_premarket

    return run_premarket()


def _invoke_daily_run():
    from app.scheduler.daily_run import run_daily

    return run_daily()


def _invoke_scoring():
    from app.scheduler.scoring_job import run_scoring

    return run_scoring()


def _guarded(name: str, job: Callable):
    """잡 예외를 삼켜 스케줄러 스레드를 살린다 — 하루 실패가 남은 잡을 죽이면 안 된다."""
    def _run():
        logger.info("[scheduler] %s 시작", name)
        try:
            result = job()
        except Exception:                               # noqa: BLE001  (스케줄러 생존 우선)
            logger.exception("[scheduler] %s 실패", name)
            return None
        logger.info("[scheduler] %s 완료 → %s", name, result)
        return result

    return _run


SCORING_EARLIEST = (10, 0)      # 판정 창(09:00–09:20) 완료 후 — 이전 채점은 오채점·고착

# 원인을 단정하지 않는다 — 미발행은 앱 중지뿐 아니라 데이터·인증 장애로도 발생한다
# (2026-07-22: 앱은 떠 있었고 만료 토큰으로 시세가 전멸했다).
SCAN_MISSED_TEXT = ("[종가베팅] 오늘 보드가 발행되지 않았습니다 — 발행 창"
                    "(15:15–15:30)이 지나 자동 스캔은 하지 않습니다(창 밖 실행은 "
                    "RVOL 분모를 20세션 오염). 내일은 15:18 전에 앱이 켜져 있어야 합니다. "
                    "원인은 보드의 퍼널·상태에서 확인하세요.")
SCAN_WINDOW_OPEN_TEXT = ("[종가베팅] 지금 발행 창(15:15–15:30) 안입니다 — 아직 오늘 "
                         "보드가 없습니다. 보드에서 '스캔' 버튼을 지금 누르면 됩니다.")


def _has_prefetch_today(run_date):
    """오늘 FINAL 프리페치가 이미 적재됐는지 — 기동 보충 중복 실행 방지."""
    from sqlalchemy import func, select

    from app.store.db import SessionLocal
    from app.store.models import FinalPrefetch

    with SessionLocal() as db:
        return bool(db.scalar(select(func.count()).select_from(FinalPrefetch)
                              .where(FinalPrefetch.run_date == run_date)))


def _board_published_today(run_date):
    from app.store.db import SessionLocal
    from app.store.models import Run

    with SessionLocal() as db:
        run = db.get(Run, run_date)
        return bool(run and run.board_published)


def file_notice_store(path=None):
    """``(was_notified, mark_notified)`` — 기동 알림 1일 1회 가드(파일 영속).

    하루에 앱을 여러 번 재시작해도 같은 알림이 반복 발송되지 않게 한다. 날짜·종류가
    바뀌면 다시 알린다. 파일 장애는 '미알림'으로 취급(알림 유실보다 중복이 낫다)."""
    import json
    from pathlib import Path

    if path is None:
        from app.config import get_settings

        path = get_settings().state_dir / "startup_notice.json"
    path = Path(path)

    def _read() -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:                               # noqa: BLE001  (결측/손상 → 빈 상태)
            return {}

    def was_notified(run_date, kind: str) -> bool:
        return _read().get(kind) == run_date.isoformat()

    def mark_notified(run_date, kind: str) -> None:
        data = _read()
        data[kind] = run_date.isoformat()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:                               # noqa: BLE001  (마커 실패는 비치명)
            pass

    return was_notified, mark_notified


def _notify_default(text: str) -> None:
    """텔레그램 우선, 실패 시 데스크톱 알림(best-effort)."""
    from app.notify import send_telegram

    if send_telegram(text):
        return
    try:
        from plyer import notification

        notification.notify(title="종가베팅", message=text, timeout=10)
    except Exception:                                   # noqa: BLE001  (알림 best-effort)
        logger.info("[startup] %s", text)


def run_startup_catchup(*, now=None, calendar=None, has_prefetch=None,
                        board_published=None, premarket=None, scoring=None,
                        notify=None, was_notified=None, mark_notified=None) -> dict:
    """서비스 기동 시 밀린 잡 보충 — APScheduler 는 꺼져 있던 시각의 잡을 복구하지 않는다.

    잡별 안전 조건이 다르다:
      - premarket : D-1 확정 데이터만 쓰므로 **언제 돌려도 안전** → 미적재면 실행
      - scoring   : 판정 창(09:00–09:20) 완료 후여야 정확 → **10시 이후에만** 실행
      - daily_run : 발행 창(15:15–15:30) 안에서만 유효 → **자동 실행 금지**(창 밖 실행은
                    마감 후 거래량을 15:20 스냅샷으로 저장해 RVOL 분모를 20세션 오염).
                    대신 미발행 상태를 알림으로 알린다.

    각 잡 실패는 삼킨다 — 보충 실패가 서버·트레이 기동을 막으면 안 된다.
    """
    from datetime import datetime, time as _time

    now = now or datetime.now()
    calendar = calendar or load_default_calendar()
    has_prefetch = has_prefetch or _has_prefetch_today
    board_published = board_published or _board_published_today
    premarket = premarket or _invoke_premarket
    scoring = scoring or _invoke_scoring
    notify = notify or _notify_default
    if was_notified is None or mark_notified is None:
        _was, _mark = file_notice_store()
        was_notified = was_notified or _was
        mark_notified = mark_notified or _mark

    run_date = now.date()
    if not calendar.is_trading_day(run_date):
        return {k: "non_trading_day" for k in ("prefetch", "scoring", "scan")}

    result: dict[str, str] = {}

    if has_prefetch(run_date):
        result["prefetch"] = "present"
    else:
        result["prefetch"] = _try("프리페치 보충", premarket)

    if now.time() < _time(*SCORING_EARLIEST):
        result["scoring"] = "too_early"
    else:
        result["scoring"] = _try("채점 보충", scoring)

    # 스캔은 절대 자동 실행하지 않는다 — 알림만(1일 1회, 재시작 도배 방지).
    _, window_end = calendar.publish_window(run_date)
    if board_published(run_date):
        result["scan"] = "published"
    elif now <= window_end:
        result["scan"] = _notify_once(run_date, "scan_window_open", SCAN_WINDOW_OPEN_TEXT,
                                      notify, was_notified, mark_notified, "window_open")
    else:
        result["scan"] = _notify_once(run_date, "scan_missed", SCAN_MISSED_TEXT,
                                      notify, was_notified, mark_notified, "missed")
    return result


def _notify_once(run_date, kind: str, text: str, notify, was_notified,
                 mark_notified, label: str) -> str:
    if was_notified(run_date, kind):
        return f"{label}_notified_already"
    notify(text)
    mark_notified(run_date, kind)
    return label


def _try(label: str, job: Callable) -> str:
    logger.info("[startup] %s 시작", label)
    try:
        job()
    except Exception:                                   # noqa: BLE001  (기동 우선)
        logger.exception("[startup] %s 실패", label)
        return "failed"
    logger.info("[startup] %s 완료", label)
    return "ran"


def build_scheduler(*, premarket=None, daily_run=None, scoring=None, scheduler=None):
    """3잡이 등록된 APScheduler 를 만든다(start 는 호출측). 콜라보레이터 주입 가능."""
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = scheduler or BackgroundScheduler(timezone="Asia/Seoul")
    jobs = (
        ("premarket", premarket or _invoke_premarket, PREMARKET_AT),
        ("scoring", scoring or _invoke_scoring, SCORING_AT),
        ("daily_run", daily_run or _invoke_daily_run, DAILY_RUN_AT),
    )
    for job_id, func, (hour, minute) in jobs:
        scheduler.add_job(
            _guarded(job_id, func), CronTrigger(day_of_week="mon-fri", hour=hour, minute=minute),
            id=job_id, name=job_id, replace_existing=True,
            misfire_grace_time=300,      # 5분 내 지연 기동은 수행(부팅 직후 등), 그 이상은 스킵
            coalesce=True,               # 밀린 실행을 1회로 합침
        )
    return scheduler


def next_run_times(scheduler) -> dict[str, str | None]:
    """트레이/상태 표시용 — 잡별 다음 실행 시각."""
    out: dict[str, str | None] = {}
    for job_id in JOB_IDS:
        job = scheduler.get_job(job_id)
        nxt = getattr(job, "next_run_time", None) if job else None
        out[job_id] = nxt.strftime("%m/%d %H:%M") if nxt else None
    return out
