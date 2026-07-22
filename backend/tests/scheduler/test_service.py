from apscheduler.schedulers.background import BackgroundScheduler

from app.scheduler.service import (
    DAILY_RUN_AT,
    JOB_IDS,
    PREMARKET_AT,
    SCORING_AT,
    build_scheduler,
    next_run_times,
)


def _scheduler(**kw):
    # 실제 start() 하지 않는다 — 등록 형상만 검증(백그라운드 스레드 미기동).
    return build_scheduler(scheduler=BackgroundScheduler(timezone="Asia/Seoul"), **kw)


def test_registers_three_jobs_with_expected_ids():
    sched = _scheduler(premarket=lambda: None, daily_run=lambda: None, scoring=lambda: None)
    assert {job.id for job in sched.get_jobs()} == set(JOB_IDS)


def test_job_times_match_windows_task_scheduler():
    # 작업스케줄러(register_tasks.ps1)와 시각이 갈리면 두 방식의 동작이 달라진다.
    sched = _scheduler(premarket=lambda: None, daily_run=lambda: None, scoring=lambda: None)
    expected = {"premarket": PREMARKET_AT, "daily_run": DAILY_RUN_AT, "scoring": SCORING_AT}
    for job_id, (hour, minute) in expected.items():
        fields = {f.name: str(f) for f in sched.get_job(job_id).trigger.fields}
        assert fields["hour"] == str(hour), job_id
        assert fields["minute"] == str(minute), job_id


def test_jobs_run_weekdays_only():
    # 주말은 비거래일 — 잡 모듈도 스스로 스킵하지만 트리거에서 먼저 거른다.
    sched = _scheduler(premarket=lambda: None, daily_run=lambda: None, scoring=lambda: None)
    fields = {f.name: str(f) for f in sched.get_job("daily_run").trigger.fields}
    assert fields["day_of_week"] == "mon-fri"


def test_scoring_never_scheduled_before_ten():
    # 10시 이전 채점은 부분 VWAP 으로 오채점되고 멱등이라 영구 고착된다.
    assert SCORING_AT >= (10, 0)


def test_daily_run_scheduled_before_snapshot_window():
    # 15:18 기동 → 모듈이 15:15–15:30 발행 창을 재검증한다.
    assert DAILY_RUN_AT < (15, 20)


def test_job_exception_is_swallowed_so_scheduler_survives():
    # 하루치 실패로 스케줄러 스레드가 죽으면 남은 잡이 전부 유실된다.
    def boom():
        raise RuntimeError("KIS down")

    sched = _scheduler(premarket=boom, daily_run=lambda: None, scoring=lambda: None)
    job = sched.get_job("premarket")
    assert job.func() is None            # 예외 전파 금지 → None


def test_successful_job_result_is_returned():
    sched = _scheduler(premarket=lambda: "OK", daily_run=lambda: None, scoring=lambda: None)
    assert sched.get_job("premarket").func() == "OK"


def test_next_run_times_reports_none_before_start():
    # start() 전에는 next_run_time 이 없다 — 트레이가 '—' 로 표시할 수 있어야 한다.
    sched = _scheduler(premarket=lambda: None, daily_run=lambda: None, scoring=lambda: None)
    times = next_run_times(sched)
    assert set(times) == set(JOB_IDS)
    assert all(v is None for v in times.values())


# ── 기동 시 밀린 잡 보충 ────────────────────────────────────
# APScheduler 는 프로세스가 꺼져 있던 시각의 잡을 보충하지 않는다(next_run_time 을
# 미래로만 계산) — 2026-07-20 실측: 14:17 부팅 → 08:30·10:05 잡이 조용히 유실.
# 안전 조건이 잡마다 다르다: 프리페치=언제나(D-1 확정), 채점=10시 이후(VWAP 창 완료),
# 스캔=발행 창 안에서만(창 밖 실행은 RVOL 분모 20세션 오염) → 스캔은 보충 대신 알림.
from datetime import date, datetime, time as _time            # noqa: E402

from app.scheduler.calendar import TradingCalendar            # noqa: E402
from app.scheduler.service import run_startup_catchup         # noqa: E402

TRADING_DAY = date(2026, 7, 22)          # 수요일
CAL = TradingCalendar(holidays={date(2026, 7, 17)}, early_close={})


def _catchup(now, *, has_prefetch=False, published=False, calls=None, notes=None):
    calls = calls if calls is not None else []
    notes = notes if notes is not None else []
    seen: set[tuple] = set()                 # 인메모리 알림 마커 — 실 state 디렉터리 격리
    return run_startup_catchup(
        now=now, calendar=CAL,
        has_prefetch=lambda d: has_prefetch,
        board_published=lambda d: published,
        premarket=lambda: calls.append("premarket") or "OK",
        scoring=lambda: calls.append("scoring") or 3,
        notify=lambda text: notes.append(text),
        was_notified=lambda d, kind: (d, kind) in seen,
        mark_notified=lambda d, kind: seen.add((d, kind)),
    ), calls, notes


def test_startup_catchup_runs_prefetch_when_missing():
    result, calls, _ = _catchup(datetime.combine(TRADING_DAY, _time(9, 0)))
    assert "premarket" in calls
    assert result["prefetch"] == "ran"


def test_startup_catchup_skips_prefetch_when_already_done():
    result, calls, _ = _catchup(datetime.combine(TRADING_DAY, _time(9, 0)),
                                has_prefetch=True)
    assert "premarket" not in calls
    assert result["prefetch"] == "present"


def test_startup_catchup_defers_scoring_before_ten():
    # 09:00–09:20 판정 창이 끝나기 전 채점은 오채점 → 멱등 가드로 고착된다.
    result, calls, _ = _catchup(datetime.combine(TRADING_DAY, _time(9, 30)))
    assert "scoring" not in calls
    assert result["scoring"] == "too_early"


def test_startup_catchup_runs_scoring_after_ten():
    result, calls, _ = _catchup(datetime.combine(TRADING_DAY, _time(14, 17)))
    assert "scoring" in calls
    assert result["scoring"] == "ran"


def test_startup_catchup_never_runs_scan_and_notifies_when_window_passed():
    # 창(15:15–15:30) 밖 스캔은 절대 자동 실행 금지 — 놓쳤다는 알림만.
    result, calls, notes = _catchup(datetime.combine(TRADING_DAY, _time(16, 0)))
    assert "daily_run" not in calls and "scan" not in calls
    assert result["scan"] == "missed"
    assert len(notes) == 1 and "발행되지 않았습니다" in notes[0]
    # 원인 단정 금지 — 미발행은 앱 중지 외에 인증·데이터 장애로도 생긴다(2026-07-22).
    assert "꺼져 있었" not in notes[0]


def test_startup_catchup_notifies_actionably_inside_window():
    # 창 안 기동인데 15:18 크론은 이미 지났다 → 지금 누르면 되는 상태임을 알린다.
    result, calls, notes = _catchup(datetime.combine(TRADING_DAY, _time(15, 22)))
    assert "daily_run" not in calls                 # 자동 실행은 여전히 안 함
    assert result["scan"] == "window_open"
    assert len(notes) == 1 and "스캔" in notes[0]


def test_startup_catchup_quiet_when_board_already_published():
    result, _, notes = _catchup(datetime.combine(TRADING_DAY, _time(16, 0)),
                                published=True)
    assert result["scan"] == "published"
    assert notes == []


def test_startup_catchup_does_nothing_on_non_trading_day():
    result, calls, notes = _catchup(datetime.combine(date(2026, 7, 17), _time(14, 0)))
    assert calls == [] and notes == []
    assert result == {"prefetch": "non_trading_day", "scoring": "non_trading_day",
                      "scan": "non_trading_day"}


def test_startup_catchup_notifies_once_per_day_despite_restarts():
    # 하루에 앱을 여러 번 껐다 켜도 같은 알림이 반복 발송되면 안 된다(폰 도배 방지).
    notes: list[str] = []
    seen: set[tuple] = set()
    kw = dict(calendar=CAL, has_prefetch=lambda d: True,
              board_published=lambda d: False,
              premarket=lambda: None, scoring=lambda: 0,
              notify=lambda text: notes.append(text),
              was_notified=lambda d, kind: (d, kind) in seen,
              mark_notified=lambda d, kind: seen.add((d, kind)))
    at = datetime.combine(TRADING_DAY, _time(16, 0))
    assert run_startup_catchup(now=at, **kw)["scan"] == "missed"
    assert run_startup_catchup(now=at, **kw)["scan"] == "missed_notified_already"
    assert run_startup_catchup(now=at, **kw)["scan"] == "missed_notified_already"
    assert len(notes) == 1                              # 3회 기동 → 알림 1회


def test_startup_catchup_notice_marker_is_per_day_and_kind(tmp_path):
    # 파일 기반 기본 구현 — 날짜·종류가 다르면 다시 알린다(다음날 재알림 보장).
    from app.scheduler.service import file_notice_store

    was_notified, mark_notified = file_notice_store(tmp_path / "notice.json")
    assert was_notified(TRADING_DAY, "scan_missed") is False
    mark_notified(TRADING_DAY, "scan_missed")
    assert was_notified(TRADING_DAY, "scan_missed") is True
    assert was_notified(TRADING_DAY, "scan_window_open") is False   # 종류 구분
    assert was_notified(date(2026, 7, 23), "scan_missed") is False  # 날짜 구분


def test_startup_catchup_survives_job_failure():
    # 보충 실패가 기동을 막으면 안 된다 — 서버·트레이는 떠야 한다.
    def boom():
        raise ConnectionError("KRX down")

    result = run_startup_catchup(
        now=datetime.combine(TRADING_DAY, _time(14, 0)), calendar=CAL,
        has_prefetch=lambda d: False, board_published=lambda d: True,
        premarket=boom, scoring=lambda: 0, notify=lambda text: None)
    assert result["prefetch"] == "failed"
    assert result["scoring"] == "ran"               # 앞 잡 실패가 뒤 잡을 막지 않는다
