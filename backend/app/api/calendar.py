from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import CalendarResponse, CalEvent, TodayInfo
from app.scheduler.calendar import TradingCalendar

router = APIRouter(tags=["calendar"])

HORIZON_DAYS = 30                       # notable 이벤트 룩어헤드 창(≈30일)
WITCHING_MONTHS = (3, 6, 9, 12)         # 네마녀(선물·옵션 동시만기) 분기월
THURSDAY = 3                            # date.weekday(): 목요일

KIND_HOLIDAY = "휴장"
KIND_EARLY_CLOSE = "조기폐장"
KIND_WITCHING = "만기"
KIND_EX_DIVIDEND = "배당락"

LABEL_HOLIDAY = "거래소 휴장"
LABEL_WITCHING = "선물·옵션 동시만기(네마녀)"
LABEL_EX_DIVIDEND = "연말 배당락"


def second_thursday(year: int, month: int) -> date:
    """해당 월 둘째주 목요일(네마녀 만기일). 결정론적 date 산술."""
    first = date(year, month, 1)
    offset = (THURSDAY - first.weekday()) % 7       # 첫 목요일까지
    return first + timedelta(days=offset + 7)       # +1주 = 둘째주


def last_trading_day_of_year(cal: TradingCalendar, year: int) -> date:
    """해당 연도 마지막 거래일(폐장 직전 영업일). 연말 배당락일 산출 기준."""
    d = date(year, 12, 31)
    while not cal.is_trading_day(d):
        d -= timedelta(days=1)
    return d


def _witching_events(today: date, end: date) -> list[dict]:
    events: list[dict] = []
    for year in (today.year, today.year + 1):
        for month in WITCHING_MONTHS:
            d = second_thursday(year, month)
            if today <= d <= end:
                events.append({"date": d, "kind": KIND_WITCHING,
                               "label": LABEL_WITCHING})
    return events


def _ex_dividend_events(cal: TradingCalendar, today: date, end: date) -> list[dict]:
    events: list[dict] = []
    for year in (today.year, today.year + 1):
        d = last_trading_day_of_year(cal, year)
        if today <= d <= end:
            events.append({"date": d, "kind": KIND_EX_DIVIDEND,
                           "label": LABEL_EX_DIVIDEND})
    return events


def _session_events(cal: TradingCalendar, today: date, end: date) -> list[dict]:
    events: list[dict] = []
    d = today
    while d <= end:
        if d.weekday() < 5 and not cal.is_trading_day(d):   # 평일 휴장만(주말 제외)
            events.append({"date": d, "kind": KIND_HOLIDAY, "label": LABEL_HOLIDAY})
        if d in cal.early_close:
            close = cal.close_time(d).strftime("%H:%M")
            events.append({"date": d, "kind": KIND_EARLY_CLOSE,
                           "label": f"조기폐장 {close}"})
        d += timedelta(days=1)
    return events


def build_calendar_response(today: date, cal: TradingCalendar,
                            horizon_days: int = HORIZON_DAYS) -> CalendarResponse:
    """오늘 세션 정보 + 향후 horizon_days 내 notable 이벤트(휴장/조기폐장/만기/배당락).
    네트워크 불필요 — 주입된 TradingCalendar 와 date 산술만 사용."""
    end = today + timedelta(days=horizon_days)
    raw = (_session_events(cal, today, end)
           + _witching_events(today, end)
           + _ex_dividend_events(cal, today, end))
    raw.sort(key=lambda e: (e["date"], e["kind"]))
    upcoming = [
        CalEvent(date=e["date"].isoformat(), kind=e["kind"], label=e["label"],
                 d_day=(e["date"] - today).days)
        for e in raw
    ]
    info = TodayInfo(
        date=today.isoformat(),
        is_trading_day=cal.is_trading_day(today),
        session_type=cal.session_type(today),
        close_time=cal.close_time(today).strftime("%H:%M"),
    )
    return CalendarResponse(today=info, upcoming=upcoming)


def get_calendar_provider() -> Callable:
    """오늘 날짜 + 운영 캘린더 공급자. 테스트는 dependency_overrides 로 주입."""
    def _provider() -> tuple[date, TradingCalendar]:
        from app.scheduler.calendar import load_default_calendar
        return date.today(), load_default_calendar()
    return _provider


@router.get("/calendar", response_model=CalendarResponse)
def get_calendar(provider: Callable = Depends(get_calendar_provider)) -> CalendarResponse:
    today, cal = provider()
    return build_calendar_response(today, cal)
