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
