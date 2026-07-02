"""장전 FINAL prefetch 번들 캐시 (00 §2).

premarket 이 ``prefetch_final`` 로 산출한 ``PrefetchBundle`` 의 종목별 FINAL 지표
(H_ref_252/H_ref_60/ATR20/20일평균거래대금/D-1 순매수)를 영속화하고, ``orchestrate_run``
이 이를 로드해 실 ``StaticCandidate`` 를 구성할 수 있게 한다(장전 prefetch 재활용).
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.models import FinalPrefetch, UniverseCache


def persist_prefetch_bundle(db: Session, bundle) -> int:
    """PrefetchBundle 의 종목별 FINAL 지표를 (run_date, ticker) 로 upsert. 저장 건수 반환.

    저장 대상 = 정적위생 계산이 성립한 종목(avg_value_20d 키). D-1 순매수는 시장 전체
    맵이므로 종목별로 결합(미존재 시 0.0)."""
    tickers = sorted(bundle.avg_value_20d.keys())
    for ticker in tickers:
        row = db.get(FinalPrefetch, (bundle.run_date, ticker))
        if row is None:
            row = FinalPrefetch(run_date=bundle.run_date, ticker=ticker)
            db.add(row)
        row.h_ref_252 = bundle.h_ref_252.get(ticker)
        row.h_ref_60 = bundle.h_ref_60.get(ticker)
        row.atr20 = bundle.atr20.get(ticker)
        row.avg_value_20d = bundle.avg_value_20d.get(ticker)
        row.d1_supply_value = bundle.net_purchases.get(ticker, 0.0)
        row.market = getattr(bundle, "market_of", {}).get(ticker)
    return len(tickers)


def persist_universe_cache(db: Session, bundle) -> int:
    """선정 유니버스(bundle.universe)를 UniverseCache 에 (ticker, as_of) 로 upsert.

    /universe 스캐너용. 모르는 필드(name/sec_type/listing 등)는 None 허용(널-안전).
    선정된 종목은 eligible=True 로 표시한다. 저장 건수 반환."""
    as_of = bundle.run_date
    market_of = getattr(bundle, "market_of", {}) or {}
    avg_value_of = getattr(bundle, "avg_value_20d", {}) or {}
    universe = list(getattr(bundle, "universe", []) or [])
    for ticker in universe:
        row = db.get(UniverseCache, (ticker, as_of))
        if row is None:
            row = UniverseCache(ticker=ticker, as_of=as_of)
            db.add(row)
        row.market = market_of.get(ticker)
        row.avg_value_20d = avg_value_of.get(ticker)
        row.eligible = True
    return len(universe)


def load_prefetch(db: Session, run_date: date) -> dict[str, FinalPrefetch]:
    """run_date FINAL 캐시를 ticker→row 로 로드(orchestrate_run 의 StaticCandidate 구성 입력)."""
    rows = db.scalars(
        select(FinalPrefetch).where(FinalPrefetch.run_date == run_date)).all()
    return {r.ticker: r for r in rows}
