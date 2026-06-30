"""장전 스케줄러 — FINAL prefetch + 헬스체크 fail-closed (00 §2).

무인자 ``health_check()->HealthResult(ok, latest_trading_day, rows, detail)`` 를 소비한다.
이 헬스체크는 지수 OHLCV뿐 아니라 **D-1 외인/기관 수급·거래대금** 조회 성공도 검증하므로,
수급 결손 시 ``ok=False`` 가 되어 런을 차단(BLOCKED)한다. 콜라보레이터는 모두 주입.
"""
from __future__ import annotations

import logging
from datetime import date, datetime

from app.scheduler.calendar import TradingCalendar, load_default_calendar

logger = logging.getLogger(__name__)


def _desktop_notify(title: str, message: str) -> None:
    try:
        from plyer import notification

        notification.notify(title=title, message=message, timeout=10)
    except Exception:                                   # noqa: BLE001  (데스크톱 알림 best-effort)
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


def run_premarket(run_date: date | None = None, *, calendar: TradingCalendar | None = None,
                  health_check=None, prefetch_final=None, session_factory=None, notify=None):
    """장전 헬스체크 → 통과 시 FINAL prefetch, 실패 시 fail-closed(BLOCKED).

    비거래일이면 아무것도 하지 않고 ``None`` 을 반환한다. 콜라보레이터 미주입 시
    실제 모듈을 지연 바인딩한다(테스트는 모두 주입).
    """
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
