from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

REGULAR_CLOSE: time = time(15, 30)                   # 정규장 마감
SNAPSHOT_OFFSET: timedelta = timedelta(minutes=10)   # 스냅샷 = 마감−10분
# 발행 창 = [스냅샷−5분, 마감]. 스케줄러가 스냅샷 직전(마감−12분)에 기동하므로 5분 여유.
PUBLISH_WINDOW_SLACK: timedelta = timedelta(minutes=5)


@dataclass(frozen=True)
class TradingCalendar:
    """KRX 거래 캘린더. 휴일/조기폐장 표를 주입받아 결정론적으로 동작한다."""

    holidays: set[date] = field(default_factory=set)
    early_close: dict[date, time] = field(default_factory=dict)

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in self.holidays

    def close_time(self, d: date) -> time:
        # 조기폐장(특수)만 마감 단축. 수능 지연개장은 표에 없으므로 15:30 유지.
        return self.early_close.get(d, REGULAR_CLOSE)

    def snapshot_at(self, d: date) -> datetime:
        return datetime.combine(d, self.close_time(d)) - SNAPSHOT_OFFSET

    def publish_window(self, d: date) -> tuple[datetime, datetime]:
        """15:20 스냅샷으로 인정되는 실행 창 = [스냅샷−5분, 마감] (정규 15:15–15:30).

        창 밖 실행은 그 시점의 누적거래량을 '15:20 스냅샷'으로 영속화해 MODELED RVOL
        분모(20세션 이동평균)를 오염시킨다 — 장중 조기 실행은 과소, 마감 후 실행은
        동시호가까지 포함해 과대 계상된다."""
        snapshot = self.snapshot_at(d)
        return snapshot - PUBLISH_WINDOW_SLACK, datetime.combine(d, self.close_time(d))

    def in_publish_window(self, moment: datetime, d: date) -> bool:
        start, end = self.publish_window(d)
        return start <= moment <= end

    def session_type(self, d: date) -> str:
        return "특수" if d in self.early_close else "정규"

    def next_trading_day(self, d: date) -> date:
        nxt = d + timedelta(days=1)
        while not self.is_trading_day(nxt):
            nxt += timedelta(days=1)
        return nxt

    def prev_trading_day(self, d: date) -> date:
        prv = d - timedelta(days=1)
        while not self.is_trading_day(prv):
            prv -= timedelta(days=1)
        return prv


HOLIDAYS_FILENAME = "holidays.json"
# prev_trading_day 역탐색이 지난 휴일을 알아야 하므로 과거분도 보존한다(연휴+설날 여유).
HOLIDAY_RETENTION_DAYS = 400


def _default_holidays_path() -> Path:
    from app.config import get_settings

    return get_settings().state_dir / HOLIDAYS_FILENAME


def _read_holidays(path: Path) -> set[date]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        return {date.fromisoformat(s) for s in raw.get("holidays", [])}
    except Exception:                                 # noqa: BLE001  (결측/손상 → 빈 표)
        return set()


def load_default_calendar(holidays_path: Path | None = None) -> TradingCalendar:
    """운영용 기본 캘린더 — ``state/holidays.json`` 의 휴일 표를 읽는다.

    표가 비면 '평일=거래일'로 동작해 공휴일에 스캔·채점이 돌아버린다
    (2026-07-17 제헌절: 휴장일 stale 시세로 RVOL 오염 + NA 채점 고착).
    갱신은 ``refresh_holidays_file`` — 프리마켓 잡이 매일 수행한다."""
    return TradingCalendar(holidays=_read_holidays(holidays_path or _default_holidays_path()),
                           early_close={})


def refresh_holidays_file(fetch_holidays=None, holidays_path: Path | None = None,
                          today: date | None = None) -> int:
    """KIS 국내휴장일조회로 휴일 표를 갱신한다. 파일 내 휴일 수를 반환.

    chk-holiday 는 from_date 이후만 반환하므로 기존 표와 **union 병합**한다 —
    월요일 ``prev_trading_day`` 가 지난 금요일 휴장을 알려면 과거분 보존이 필수.
    보존창 밖 항목은 프루닝. 조회 실패 시 기존 파일을 그대로 둔다(best-effort)."""
    path = Path(holidays_path or _default_holidays_path())
    today = today or datetime.now().date()
    existing = _read_holidays(path)
    if fetch_holidays is None:
        from app.data.kis_client import build_default_client

        fetch_holidays = build_default_client().get_holidays
    try:
        fetched = set(fetch_holidays(today))
    except Exception as exc:                          # noqa: BLE001  (외부 IO — graceful)
        logger.warning("휴장일 표 갱신 실패(기존 표 유지): %s", exc)
        return len(existing)
    cutoff = today - timedelta(days=HOLIDAY_RETENTION_DAYS)
    merged = {d for d in existing | fetched if d >= cutoff}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"updated_at": datetime.now().isoformat(),
                                "holidays": sorted(d.isoformat() for d in merged)},
                               indent=1), encoding="utf-8")
    return len(merged)
