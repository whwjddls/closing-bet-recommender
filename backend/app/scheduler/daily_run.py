"""15:20 런 스케줄러 — 커버리지 게이트·top3 알림 (00 §3).

거래일·세션을 ``TradingCalendar`` 로 판정해 스냅샷 시각(정규=15:20 / 특수=마감−10)을
산출하고, 주입된 ``run_pipeline``(= 00 §3 ``orchestrate_run`` 바인딩, ``RunResult`` 반환)을
호출한다. ``data_available=False`` 또는 ``kis_coverage_pct<70`` 이면 **미발행(UNPUBLISHED)**,
아니면 추천/레짐을 DB에 영속화 + JSON 스냅샷 + ``runs.status=OK`` + top3 알림.
콜라보레이터는 모두 주입(테스트는 네트워크 없이 동작).
"""
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
    except Exception:                                   # noqa: BLE001  (데스크톱 알림 best-effort)
        logger.info("[NOTIFY] %s: %s", title, message)


def _default_run_pipeline(run_date: date, snapshot_at: datetime):
    """프로덕션 기본 seam — 라이브 pykrx/KIS/DART 클라이언트 + LiveBrokerDataAdapter +
    store 페이사드로 바인딩된 00 §3 ``orchestrate_run`` 을 호출한다.

    무거운/네트워크 의존은 ``live_binding`` 내부에서 지연 임포트한다(테스트는 run_pipeline 주입).
    크리덴셜 미설정 시 fail-closed 로 명시적 실패한다.
    """
    from app.scheduler.live_binding import build_live_run_pipeline

    return build_live_run_pipeline()(run_date, snapshot_at)


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
            target_price=r.target_price, stop_price=r.stop_price,
            spark=r.spark, base_flag=r.base_flag,
            exp_close=getattr(r, "exp_close", None),
            supply_today=getattr(r, "supply_today", None),
            provisional_flag=True, created_at=now,
        ))


def _persist_regimes(db, run_date, result):
    from app.store.models import RegimeSnapshot

    db.query(RegimeSnapshot).filter(RegimeSnapshot.run_date == run_date).delete()
    for rg in result.regimes.values():
        db.add(RegimeSnapshot(
            run_date=run_date, market=rg.market, index_level=rg.index_level, ma5=rg.ma5,
            ma5_prev=getattr(rg, "ma5_prev", None), cond_a=rg.cond_a, cond_b=rg.cond_b,
            regime_mult=rg.regime_mult,
        ))


def _payload(run_date, session_type, result):
    return {
        "run_date": run_date.isoformat(),
        "session_type": session_type,
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
              run_pipeline=None, session_factory=None, notify=None, snapshots=None,
              now: datetime | None = None, allow_outside_window: bool = False):
    """15:20 런 파이프라인. 비거래일이면 아무것도 하지 않고 ``None`` 을 반환한다.

    발행 창(정규 15:15–15:30) 밖 실행은 ``OUTSIDE_WINDOW`` 로 즉시 중단한다 — 라이브
    조회조차 하지 않으므로 어떤 쓰기도 발생하지 않는다. 창 밖에서 파이프라인을 돌리면
    그 시점 누적거래량이 '15:20 스냅샷'으로 upsert 되어 MODELED RVOL 분모(20세션
    이동평균)를 오염시키고, 살 수 없는 픽이 익일 채점 대상으로 남는다.
    ``allow_outside_window=True`` 는 백필/디버깅 전용 탈출구.

    ``run_pipeline`` 은 ``(run_date, snapshot_at) -> RunResult``(00 §3) 콜라보레이터로,
    미주입 시 라이브 ``orchestrate_run`` seam 을 바인딩한다(테스트는 모두 주입).
    """
    calendar = calendar or load_default_calendar()
    run_date = run_date or datetime.now().date()
    if not calendar.is_trading_day(run_date):
        logger.info("non-trading day %s, daily_run skip", run_date)
        return None

    now = now or datetime.now()
    if not allow_outside_window and not calendar.in_publish_window(now, run_date):
        start, end = calendar.publish_window(run_date)
        logger.warning("발행 창 밖 실행 차단(%s) — 창 %s~%s, 현재 %s. 거래량 스냅샷 오염 방지.",
                       run_date, start.strftime("%H:%M"), end.strftime("%H:%M"),
                       now.strftime("%H:%M"))
        return "OUTSIDE_WINDOW"

    run_pipeline = run_pipeline or _default_run_pipeline
    if session_factory is None:
        from app.store.db import SessionLocal as session_factory
    if snapshots is None:
        from app.store import snapshots
    notify = notify or _desktop_notify

    snapshot_at = calendar.snapshot_at(run_date)         # 정규=15:20 / 특수=마감−10
    session_type = calendar.session_type(run_date)       # 캘린더가 세션 정본
    started = datetime.now()
    result = run_pipeline(run_date, snapshot_at)         # 00 §3 orchestrate_run → RunResult

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

    snapshots.write_snapshot(run_date, _payload(run_date, session_type, result))
    _notify_top3(result, notify)
    return "OK"


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    run_daily()


if __name__ == "__main__":
    main()
