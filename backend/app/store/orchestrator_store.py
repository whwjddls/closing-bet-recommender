"""orchestrate_run 이 소비하는 store 페이사드 (RVOL 스냅샷 생산자 + 레짐 영속화).

DB 세션을 감싸 ``upsert_volume_snapshot`` / ``trailing_volume`` / ``save_regime`` 만
노출한다(엔진은 SQLAlchemy 를 모른다 — 테스트는 인메모리 페이크로 대체 가능).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.models import RegimeSnapshot, VolumeSnapshot


class OrchestratorStore:
    def __init__(self, db: Session):
        self._db = db

    def upsert_volume_snapshot(self, ticker: str, run_date: date,
                               cum_volume, cum_value) -> None:
        row = self._db.get(VolumeSnapshot, (ticker, run_date))
        if row is None:
            row = VolumeSnapshot(ticker=ticker, snapshot_date=run_date)
            self._db.add(row)
        row.cum_volume_1520 = int(cum_volume) if cum_volume is not None else None
        row.cum_value_1520 = int(cum_value) if cum_value is not None else None

    def trailing_volume(self, ticker: str, before: date) -> list[float]:
        rows = self._db.scalars(
            select(VolumeSnapshot)
            .where(VolumeSnapshot.ticker == ticker,
                   VolumeSnapshot.snapshot_date < before)
            .order_by(VolumeSnapshot.snapshot_date)
        ).all()
        return [float(r.cum_volume_1520) for r in rows if r.cum_volume_1520 is not None]

    def save_regime(self, run_date: date, market: str, info) -> None:
        row = self._db.get(RegimeSnapshot, (run_date, market))
        if row is None:
            row = RegimeSnapshot(run_date=run_date, market=market)
            self._db.add(row)
        row.index_level = info.index_level
        row.ma5 = info.ma5
        row.ma5_prev = getattr(info, "ma5_prev", None)
        row.cond_a = info.cond_a
        row.cond_b = info.cond_b
        row.regime_mult = info.regime_mult

    def load_prefetch(self, run_date: date):
        """장전 영속화된 FINAL 캐시(00 §2)를 ticker→FinalPrefetch 로 로드.

        orchestrate_run 이 StaticCandidate 의 FINAL 지표(H_ref/ATR20/avg_value_20d/
        D-1 순매수)를 채우는 데 사용한다."""
        from app.store import final_cache

        return final_cache.load_prefetch(self._db, run_date)

    def load_names(self, run_date: date) -> dict[str, str]:
        """run_date 이하 최신 as_of 의 universe_cache 종목명 맵(ticker→name).

        프리페치 경로 후보는 이름원이 없어 name 이 티커로 남는다 — orchestrate_run 이
        이 맵으로 오버레이한다. 빈 이름/티커와 동일한 이름은 제외."""
        from sqlalchemy import func

        from app.store.models import UniverseCache

        latest = self._db.scalar(select(func.max(UniverseCache.as_of))
                                 .where(UniverseCache.as_of <= run_date))
        if latest is None:
            return {}
        rows = self._db.scalars(
            select(UniverseCache).where(UniverseCache.as_of == latest)).all()
        return {r.ticker: r.name for r in rows if r.name and r.name != r.ticker}
