from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


class Base(DeclarativeBase):
    pass


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        UniqueConstraint("run_date", "ticker", name="uq_rec_run_date_ticker"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str | None] = mapped_column(String)
    market: Mapped[str] = mapped_column(String, nullable=False, default="KOSPI")
    rank: Mapped[int | None] = mapped_column(Integer)
    price_provisional: Mapped[float | None] = mapped_column(Float)
    buy_price_provisional: Mapped[float | None] = mapped_column(Float)
    buy_price_final: Mapped[float | None] = mapped_column(Float)
    s_shin: Mapped[float | None] = mapped_column(Float)
    s_geo: Mapped[float | None] = mapped_column(Float)
    rvol_confirm: Mapped[float | None] = mapped_column(Float)
    supply_tilt: Mapped[float | None] = mapped_column(Float)
    regime_mult: Mapped[float | None] = mapped_column(Float)
    veto: Mapped[int | None] = mapped_column(Integer)
    core: Mapped[float | None] = mapped_column(Float)
    final: Mapped[float | None] = mapped_column(Float)
    grade: Mapped[str | None] = mapped_column(String)
    near_252: Mapped[float | None] = mapped_column(Float)
    near_60: Mapped[float | None] = mapped_column(Float)
    rvol: Mapped[float | None] = mapped_column(Float)
    target_price: Mapped[float | None] = mapped_column(Float)
    stop_price: Mapped[float | None] = mapped_column(Float)
    spark: Mapped[list[float] | None] = mapped_column(JSON)       # 스파크라인 series
    base_flag: Mapped[bool | None] = mapped_column(Boolean)       # 베이스 돌파 배지
    provisional_flag: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    performances: Mapped[list["Performance"]] = relationship(
        back_populates="recommendation")


class Performance(Base):
    __tablename__ = "performance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rec_id: Mapped[int] = mapped_column(
        ForeignKey("recommendations.id"), nullable=False)
    eval_date: Mapped[dt.date | None] = mapped_column(Date)
    buy_price_final: Mapped[float | None] = mapped_column(Float)
    vwap_0900_1000: Mapped[float | None] = mapped_column(Float)
    morning_return: Mapped[float | None] = mapped_column(Float)
    outcome: Mapped[str | None] = mapped_column(String)          # SUCCESS/FAIL/NA
    dart_overnight_flag: Mapped[bool | None] = mapped_column(Boolean)
    scored_at: Mapped[dt.datetime | None] = mapped_column(DateTime)

    recommendation: Mapped["Recommendation"] = relationship(
        back_populates="performances")


class VolumeSnapshot(Base):
    __tablename__ = "volume_snapshots"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    snapshot_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    cum_volume_1520: Mapped[int | None] = mapped_column(Integer)
    cum_value_1520: Mapped[int | None] = mapped_column(Integer)


class UniverseCache(Base):
    __tablename__ = "universe_cache"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    as_of: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    name: Mapped[str | None] = mapped_column(String)
    market: Mapped[str | None] = mapped_column(String)
    sec_type: Mapped[str | None] = mapped_column(String)
    avg_value_20d: Mapped[float | None] = mapped_column(Float)
    is_managed: Mapped[bool | None] = mapped_column(Boolean)
    is_warning: Mapped[bool | None] = mapped_column(Boolean)
    is_caution: Mapped[bool | None] = mapped_column(Boolean)
    listing_days: Mapped[int | None] = mapped_column(Integer)
    eligible: Mapped[bool | None] = mapped_column(Boolean)


class RegimeSnapshot(Base):
    __tablename__ = "regime_snapshots"

    run_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    market: Mapped[str] = mapped_column(String, primary_key=True)
    index_level: Mapped[float | None] = mapped_column(Float)
    ma5: Mapped[float | None] = mapped_column(Float)
    ma5_prev: Mapped[float | None] = mapped_column(Float)
    cond_a: Mapped[bool | None] = mapped_column(Boolean)
    cond_b: Mapped[bool | None] = mapped_column(Boolean)
    regime_mult: Mapped[float | None] = mapped_column(Float)


class CorpCodeMap(Base):
    __tablename__ = "corp_code_map"

    corp_code: Mapped[str] = mapped_column(String, primary_key=True)
    ticker: Mapped[str | None] = mapped_column(String)
    name: Mapped[str | None] = mapped_column(String)
    updated_at: Mapped[dt.datetime | None] = mapped_column(DateTime)


class Run(Base):
    __tablename__ = "runs"

    run_date: Mapped[dt.date] = mapped_column(Date, primary_key=True)
    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime)
    status: Mapped[str | None] = mapped_column(String)       # OK/UNPUBLISHED/BLOCKED
    kis_coverage_pct: Mapped[float | None] = mapped_column(Float)
    board_published: Mapped[bool | None] = mapped_column(Boolean)
    session_type: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(String)
