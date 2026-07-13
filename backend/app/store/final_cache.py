"""장전 FINAL prefetch 번들 캐시 (00 §2).

premarket 이 ``prefetch_final`` 로 산출한 ``PrefetchBundle`` 의 종목별 FINAL 지표
(H_ref_252/H_ref_60/ATR20/20일평균거래대금/D-1 순매수)를 영속화하고, ``orchestrate_run``
이 이를 로드해 실 ``StaticCandidate`` 를 구성할 수 있게 한다(장전 prefetch 재활용).
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.store.models import FinalPrefetch, UniverseCache


def persist_prefetch_bundle(db: Session, bundle) -> int:
    """PrefetchBundle 의 종목별 FINAL 지표를 run_date 단위로 **교체** 저장. 저장 건수 반환.

    저장 대상 = 정적위생 계산이 성립한 종목(avg_value_20d 키). D-1 순매수는 시장 전체
    맵이므로 종목별로 결합(미존재 시 0.0).

    같은 날 재실행 시 이전 행을 먼저 지운다 — 순수 upsert 였을 때는 유니버스가 바뀌면
    옛 행이 남아 후보풀이 신·구 합집합으로 부풀고, 잘못된 D-1 로 계산된 stale 행
    (수급 0 등)이 그대로 15:20 런에 흘러들었다."""
    tickers = sorted(bundle.avg_value_20d.keys())
    db.query(FinalPrefetch).filter(FinalPrefetch.run_date == bundle.run_date).delete()
    db.flush()
    for ticker in tickers:
        db.add(FinalPrefetch(
            run_date=bundle.run_date, ticker=ticker,
            h_ref_252=bundle.h_ref_252.get(ticker),
            h_ref_60=bundle.h_ref_60.get(ticker),
            atr20=bundle.atr20.get(ticker),
            avg_value_20d=bundle.avg_value_20d.get(ticker),
            d1_supply_value=bundle.net_purchases.get(ticker, 0.0),
            market=getattr(bundle, "market_of", {}).get(ticker)))
    return len(tickers)


def persist_universe_cache(db: Session, bundle, names: dict | None = None) -> int:
    """선정 유니버스(bundle.universe)를 UniverseCache 에 (ticker, as_of) 로 upsert.

    /universe 스캐너용. 종목명은 벌크 맵(names)으로 채운다 — 미주입 시 KRX에서 1회
    벌크 조회(stock_names_bulk, 개별 200회 회피). 선정 종목은 eligible=True. 저장 건수 반환."""
    as_of = bundle.run_date
    market_of = getattr(bundle, "market_of", {}) or {}
    avg_value_of = getattr(bundle, "avg_value_20d", {}) or {}
    universe = list(getattr(bundle, "universe", []) or [])
    if names is None:
        from app.data.pykrx_client import stock_names_bulk

        frm_s = (as_of - timedelta(days=10)).strftime("%Y%m%d")
        to_s = (as_of - timedelta(days=1)).strftime("%Y%m%d")
        names = stock_names_bulk(frm_s, to_s)
    for ticker in universe:
        row = db.get(UniverseCache, (ticker, as_of))
        if row is None:
            row = UniverseCache(ticker=ticker, as_of=as_of)
            db.add(row)
        row.name = names.get(ticker) or row.name
        row.market = market_of.get(ticker)
        row.avg_value_20d = avg_value_of.get(ticker)
        row.eligible = True
    return len(universe)


def load_prefetch(db: Session, run_date: date) -> dict[str, FinalPrefetch]:
    """run_date FINAL 캐시를 ticker→row 로 로드(orchestrate_run 의 StaticCandidate 구성 입력)."""
    rows = db.scalars(
        select(FinalPrefetch).where(FinalPrefetch.run_date == run_date)).all()
    return {r.ticker: r for r in rows}
