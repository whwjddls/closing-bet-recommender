from datetime import date, datetime, time

from app.scheduler.calendar import REGULAR_CLOSE, SNAPSHOT_OFFSET, TradingCalendar

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
