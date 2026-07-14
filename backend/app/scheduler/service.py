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
