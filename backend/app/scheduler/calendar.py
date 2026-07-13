from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

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


def load_default_calendar() -> TradingCalendar:
    """운영용 기본 캘린더. 휴일/조기폐장 표는 운영 데이터(번들 JSON/pykrx)에서 주입.
    스케줄러는 테스트에서 명시적 캘린더를 주입하므로 여기서는 빈 표로 시작한다."""
    return TradingCalendar(holidays=set(), early_close={})
