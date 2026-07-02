from datetime import date, time

from app.api.calendar import (
    build_calendar_response,
    get_calendar_provider,
    get_holidays_provider,
    last_trading_day_of_year,
    second_thursday,
)
from app.scheduler.calendar import TradingCalendar


# ── 순수 date 산술: 둘째주 목요일(네마녀 만기) ───────────────
def test_second_thursday_matches_known_dates():
    assert second_thursday(2026, 6) == date(2026, 6, 11)     # 2026-06 둘째주 목
    assert second_thursday(2026, 3) == date(2026, 3, 12)
    assert second_thursday(2026, 12) == date(2026, 12, 10)


def test_last_trading_day_of_year_skips_year_end_holiday():
    cal = TradingCalendar(holidays={date(2026, 12, 31)})     # 폐장일 휴장
    assert last_trading_day_of_year(cal, 2026) == date(2026, 12, 30)


# ── build_calendar_response: today 정보 + 이벤트 창 ─────────
def test_today_info_regular_session():
    cal = TradingCalendar()
    resp = build_calendar_response(date(2026, 6, 1), cal)    # 월요일 정규
    assert resp.today.date == "2026-06-01"
    assert resp.today.is_trading_day is True
    assert resp.today.session_type == "정규"
    assert resp.today.close_time == "15:30"


def test_upcoming_includes_holiday_early_close_and_witching():
    cal = TradingCalendar(
        holidays={date(2026, 7, 1)},                         # 창 내 휴장(day 30)
        early_close={date(2026, 6, 29): time(14, 0)},        # 창 내 조기폐장(day 28)
    )
    resp = build_calendar_response(date(2026, 6, 1), cal)
    by_kind = {e.kind: e for e in resp.upcoming}
    assert by_kind["휴장"].date == "2026-07-01"
    assert by_kind["휴장"].d_day == 30
    assert by_kind["조기폐장"].date == "2026-06-29"
    assert by_kind["조기폐장"].label == "조기폐장 14:00"
    assert by_kind["만기"].date == "2026-06-11"              # 둘째주 목(네마녀)
    assert by_kind["만기"].d_day == 10
    # 이벤트는 날짜 오름차순
    dates = [e.date for e in resp.upcoming]
    assert dates == sorted(dates)


def test_upcoming_includes_year_end_ex_dividend():
    cal = TradingCalendar(holidays={date(2026, 12, 31)})     # 폐장일 휴장
    resp = build_calendar_response(date(2026, 12, 1), cal)
    by_kind = {e.kind: e for e in resp.upcoming}
    assert by_kind["배당락"].date == "2026-12-30"            # 마지막 거래일 = 배당락
    assert by_kind["휴장"].date == "2026-12-31"
    assert by_kind["만기"].date == "2026-12-10"


def test_no_events_when_calendar_clear_and_no_quarter_month():
    cal = TradingCalendar()
    resp = build_calendar_response(date(2026, 7, 15), cal)   # 7월엔 네마녀/배당락 없음
    assert resp.upcoming == []


# ── 엔드포인트: 의존성 주입으로 결정론적 응답 ──────────────
def test_calendar_endpoint_serializes(client):
    cal = TradingCalendar(holidays={date(2026, 7, 1)})

    def _fake_provider():
        return date(2026, 6, 1), cal

    client.app.dependency_overrides[get_calendar_provider] = lambda: _fake_provider
    resp = client.get("/calendar")
    assert resp.status_code == 200
    body = resp.json()
    assert body["today"]["date"] == "2026-06-01"
    assert body["today"]["is_trading_day"] is True
    kinds = {e["kind"] for e in body["upcoming"]}
    assert "휴장" in kinds
    assert "만기" in kinds


def test_calendar_endpoint_default_provider_no_network(client):
    # 미오버라이드 → load_default_calendar(빈 표) + 빈 KIS 휴장일. 네트워크 없이 200.
    client.app.dependency_overrides[get_holidays_provider] = lambda: (lambda d: [])
    resp = client.get("/calendar")
    assert resp.status_code == 200
    assert "today" in resp.json()


# ── KIS 휴장일 merge(F2) ───────────────────────────────────
def test_kis_holidays_merged_as_holiday_events():
    cal = TradingCalendar()                                  # 결정론 표 비어있음
    kis = [date(2026, 6, 15), date(2026, 6, 20)]            # 창 내 KIS 휴장일
    resp = build_calendar_response(date(2026, 6, 1), cal, kis_holidays=kis)
    holidays = {e.date for e in resp.upcoming if e.kind == "휴장"}
    assert "2026-06-15" in holidays
    assert "2026-06-20" in holidays


def test_kis_holiday_deduped_with_calendar_holiday():
    cal = TradingCalendar(holidays={date(2026, 7, 1)})       # 결정론 휴장(창 day30)
    kis = [date(2026, 7, 1)]                                 # 동일일 KIS 휴장
    resp = build_calendar_response(date(2026, 6, 1), cal, kis_holidays=kis)
    dupes = [e for e in resp.upcoming if e.date == "2026-07-01" and e.kind == "휴장"]
    assert len(dupes) == 1                                   # 중복 제거


def test_kis_holidays_outside_horizon_ignored():
    cal = TradingCalendar()
    kis = [date(2026, 9, 1)]                                 # 30일 창 밖
    resp = build_calendar_response(date(2026, 6, 1), cal, kis_holidays=kis)
    assert all(e.date != "2026-09-01" for e in resp.upcoming)


def test_calendar_endpoint_merges_kis_holidays(client):
    cal = TradingCalendar()

    client.app.dependency_overrides[get_calendar_provider] = (
        lambda: (lambda: (date(2026, 6, 1), cal)))
    client.app.dependency_overrides[get_holidays_provider] = (
        lambda: (lambda d: [date(2026, 6, 15)]))
    body = client.get("/calendar").json()
    holidays = {e["date"] for e in body["upcoming"] if e["kind"] == "휴장"}
    assert "2026-06-15" in holidays


def test_calendar_endpoint_graceful_when_kis_holidays_fail(client):
    cal = TradingCalendar(holidays={date(2026, 7, 1)})

    def _boom(d):
        raise ConnectionError("KIS outage")

    client.app.dependency_overrides[get_calendar_provider] = (
        lambda: (lambda: (date(2026, 6, 1), cal)))
    client.app.dependency_overrides[get_holidays_provider] = lambda: _boom
    resp = client.get("/calendar")
    assert resp.status_code == 200                           # graceful — 500 아님
    kinds = {e["kind"] for e in resp.json()["upcoming"]}
    assert "휴장" in kinds                                   # 결정론 휴장은 유지
