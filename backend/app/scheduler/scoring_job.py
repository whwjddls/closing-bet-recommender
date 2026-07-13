"""익일 채점 스케줄러 — N/A·DART 오버나잇 재스캔·룩어헤드 가드 (스펙 §6.3/§6.4).

익일 **10:00 이후**에 실행(09:00–10:00 VWAP 창 완료 후 — 이전에 돌리면 부분
VWAP으로 오채점되고 멱등이라 고착됨). ``run_date = prev_trading_day(eval_date)`` 로 역매핑하고,
매수가 = **확정 종가 close[run_date]**, 청산 = **오전 VWAP(eval_date) 09:00–10:00**.
VWAP 결측/잠김 → outcome=NA(분모 제외). DART 오버나잇 공시 발생 시 재스캔 플래그.
**룩어헤드 가드**: close 는 run_date(t)로만, VWAP 는 eval_date(t+1)로만 조회한다.
멱등: 이미 채점된 추천은 건너뛴다. 콜라보레이터는 모두 주입.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time

from app.config import load_env
from app.scheduler.calendar import TradingCalendar, load_default_calendar

logger = logging.getLogger(__name__)


def run_scoring(eval_date: date | None = None, *, calendar: TradingCalendar | None = None,
                session_factory=None, fetch_confirmed_close=None, fetch_morning_vwap=None,
                overnight_scan=None):
    """전 거래일(run_date) 픽을 eval_date 오전 VWAP 으로 채점한다.

    비거래일이면 아무것도 하지 않고 ``None`` 을 반환한다. 콜라보레이터 미주입 시
    실제 모듈을 지연 바인딩한다(테스트는 모두 주입). 채점 건수를 반환한다.
    """
    calendar = calendar or load_default_calendar()
    eval_date = eval_date or datetime.now().date()
    if not calendar.is_trading_day(eval_date):
        logger.info("non-trading day %s, scoring skip", eval_date)
        return None

    run_date = calendar.prev_trading_day(eval_date)     # t→t+1 역매핑 (룩어헤드 가드)

    if session_factory is None:
        from app.store.db import SessionLocal as session_factory
    if fetch_confirmed_close is None:
        from app.data.pykrx_client import fetch_confirmed_close
    if fetch_morning_vwap is None:
        from app.data.kis_client import fetch_morning_vwap
    if overnight_scan is None:
        from app.data.dart_client import overnight_scan

    from sqlalchemy import select

    from app.store.models import Performance, Recommendation

    scored = 0
    with session_factory() as db:
        recs = db.scalars(select(Recommendation).where(Recommendation.run_date == run_date)).all()
        for rec in recs:
            if db.scalar(select(Performance).where(Performance.rec_id == rec.id)):
                continue   # 멱등: 이미 채점됨

            try:
                close_t = fetch_confirmed_close(rec.ticker, run_date)  # close[t] (확정)
            except Exception as exc:                                   # noqa: BLE001
                # 확정 종가 결측/조회 실패 → 해당 종목만 N/A(분모 제외), 배치는 계속 (스펙 §4.2)
                logger.warning("confirmed close missing for %s on %s: %s; marking N/A",
                               rec.ticker, run_date, exc)
                close_t = None
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
    load_env()          # 작업스케줄러 실행 경로 — main.py 를 거치지 않아 여기서 .env 주입
    run_scoring()


if __name__ == "__main__":
    main()
