import datetime as dt

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.store.models import (
    Base,
    Recommendation,
    Performance,
    VolumeSnapshot,
    UniverseCache,
    RegimeSnapshot,
    CorpCodeMap,
    Run,
)


@pytest.fixture
def session():
    # 00 §1 계약: Base.metadata.create_all(engine) + Session (격리 위해 in-memory)
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False,
                           expire_on_commit=False, future=True)
    with factory() as s:
        yield s


def test_all_seven_tables_created():
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    names = set(Base.metadata.tables.keys())
    assert {
        "recommendations",
        "performance",
        "volume_snapshots",
        "universe_cache",
        "regime_snapshots",
        "corp_code_map",
        "runs",
    } <= names


def test_recommendation_roundtrip_preserves_provisional_and_final(session):
    rec = Recommendation(
        run_date=dt.date(2026, 6, 30), ticker="000660", name="SK하이닉스",
        market="KOSPI", rank=1, price_provisional=24500.0,
        buy_price_provisional=24500.0, buy_price_final=None,
        s_shin=1.164, s_geo=0.834, rvol_confirm=0.934, supply_tilt=1.032,
        regime_mult=1.0, veto=1, core=1.122, final=1.122, grade="S",
        near_252=1.0208, near_60=1.0426, rvol=2.5,
        target_price=25000.0, stop_price=23765.0,
        spark=[1.0, 1.1, 1.2], base_flag=True,
        provisional_flag=True, created_at=dt.datetime(2026, 6, 30, 15, 20),
    )
    session.add(rec)
    session.commit()
    assert rec.id == 1
    # expire 후 재조회 → SQLite에서 실제 역직렬화(특히 spark JSON 컬럼) 검증
    session.expire_all()
    fetched = session.scalars(
        select(Recommendation).where(
            Recommendation.run_date == dt.date(2026, 6, 30))
    ).all()
    assert len(fetched) == 1
    got = fetched[0]
    # 잠정-확정 갭: 둘 다 보관(확정 전 final=None)
    assert got.buy_price_provisional == 24500.0
    assert got.buy_price_final is None
    assert got.provisional_flag is True
    assert got.grade == "S"
    # spark(JSON list[float])·base_flag·s_geo 보존(아키텍처 §4 전 컬럼)
    assert got.spark == [1.0, 1.1, 1.2]
    assert got.base_flag is True
    assert got.s_geo == 0.834


def test_recommendation_unique_run_date_ticker(session):
    session.add(Recommendation(run_date=dt.date(2026, 6, 30),
                               ticker="000660", name="x", market="KOSPI"))
    session.commit()
    session.add(Recommendation(run_date=dt.date(2026, 6, 30),
                               ticker="000660", name="y", market="KOSPI"))
    with pytest.raises(IntegrityError):
        session.commit()         # UNIQUE(run_date, ticker) 위반
    session.rollback()


def test_regime_snapshot_pk_run_date_market(session):
    session.add(RegimeSnapshot(
        run_date=dt.date(2026, 6, 30), market="KOSPI", index_level=2650.0,
        ma5=2600.0, ma5_prev=2590.0, cond_a=True, cond_b=True, regime_mult=1.0))
    session.add(RegimeSnapshot(
        run_date=dt.date(2026, 6, 30), market="KOSDAQ", index_level=850.0,
        ma5=840.0, ma5_prev=845.0, cond_a=True, cond_b=False, regime_mult=0.5))
    session.commit()
    # 같은 run_date 다른 market → 2행
    assert len(session.scalars(select(RegimeSnapshot)).all()) == 2
    # 동일 PK(run_date, market) merge → 갱신(행수 불변)
    session.merge(RegimeSnapshot(
        run_date=dt.date(2026, 6, 30), market="KOSPI", index_level=2700.0,
        ma5=2610.0, ma5_prev=2600.0, cond_a=True, cond_b=True, regime_mult=1.0))
    session.commit()
    assert len(session.scalars(select(RegimeSnapshot)).all()) == 2
    kospi = session.get(RegimeSnapshot, (dt.date(2026, 6, 30), "KOSPI"))
    assert kospi.index_level == 2700.0


def test_corp_code_map_pk(session):
    session.add(CorpCodeMap(corp_code="00126380", ticker="005930",
                            name="삼성전자"))
    session.commit()
    session.merge(CorpCodeMap(corp_code="00126380", ticker="005930",
                              name="삼성전자(정정)"))
    session.commit()
    assert len(session.scalars(select(CorpCodeMap)).all()) == 1
    assert session.get(CorpCodeMap, "00126380").name == "삼성전자(정정)"


def test_volume_snapshot_pk_ticker_date(session):
    session.add(VolumeSnapshot(ticker="000660", snapshot_date=dt.date(2026, 6, 30),
                               cum_volume_1520=1000, cum_value_1520=24500000))
    session.commit()
    session.merge(VolumeSnapshot(ticker="000660", snapshot_date=dt.date(2026, 6, 30),
                                 cum_volume_1520=2000, cum_value_1520=49000000))
    session.commit()
    rows = session.scalars(select(VolumeSnapshot)).all()
    assert len(rows) == 1
    assert rows[0].cum_volume_1520 == 2000


def test_run_roundtrip(session):
    session.add(Run(
        run_date=dt.date(2026, 6, 30),
        started_at=dt.datetime(2026, 6, 30, 15, 20),
        finished_at=dt.datetime(2026, 6, 30, 15, 20, 14), status="OK",
        kis_coverage_pct=92.0, board_published=True,
        session_type="정규", reason=""))
    session.commit()
    session.expire_all()
    got = session.get(Run, dt.date(2026, 6, 30))
    assert got.status == "OK"
    assert got.board_published is True


def test_performance_fk_to_recommendation(session):
    rec = Recommendation(run_date=dt.date(2026, 6, 30), ticker="000660",
                         name="SK하이닉스", market="KOSPI")
    session.add(rec)
    session.commit()
    session.add(Performance(
        rec_id=rec.id, eval_date=dt.date(2026, 7, 1), buy_price_final=24800.0,
        vwap_0900_1000=25010.0, morning_return=0.0085, outcome="SUCCESS",
        dart_overnight_flag=False, scored_at=dt.datetime(2026, 7, 1, 10, 0)))
    session.commit()
    perf = session.scalars(select(Performance)).one()
    assert perf.recommendation.ticker == "000660"   # relationship 역참조
    assert perf.outcome == "SUCCESS"


def test_universe_cache_pk_ticker_as_of(session):
    session.add(UniverseCache(
        ticker="000660", as_of=dt.date(2026, 6, 29), name="SK하이닉스",
        market="KOSPI", sec_type="EQUITY", avg_value_20d=8.0e10,
        is_managed=False, is_warning=False, is_caution=False,
        listing_days=5000, eligible=True))
    session.commit()
    got = session.get(UniverseCache, ("000660", dt.date(2026, 6, 29)))
    assert got.eligible is True
    assert got.avg_value_20d == 8.0e10


# ── 경량 자동 마이그레이션: 모델에 추가된 nullable 컬럼을 기존 테이블에 보강 ──
def test_ensure_columns_adds_missing_nullable_columns(tmp_path):
    import sqlite3
    from sqlalchemy import create_engine, inspect
    from app.store.db import _ensure_columns

    db = tmp_path / "old.sqlite"
    raw = sqlite3.connect(db)
    # 구스키마 시뮬레이션: exp_close/supply_today 없는 recommendations
    raw.execute("CREATE TABLE recommendations (id INTEGER PRIMARY KEY, run_date DATE, ticker VARCHAR)")
    raw.commit(); raw.close()

    eng = create_engine(f"sqlite:///{db.as_posix()}", future=True)
    _ensure_columns(eng)
    cols = {c["name"] for c in inspect(eng).get_columns("recommendations")}
    assert "exp_close" in cols and "supply_today" in cols     # 누락 컬럼 자동 추가
    assert "spark" in cols and "base_flag" in cols            # 과거 추가분도 커버
    _ensure_columns(eng)                                      # 멱등(재실행 무해)


def test_persist_prefetch_bundle_replaces_prior_rows_for_same_date(session):
    # 같은 날 재실행(유니버스 변경) 시 옛 행이 남으면 15:20 후보풀이 신·구 합집합으로
    # 부풀고, 잘못된 D-1 로 계산된 stale 행(수급 0)이 그대로 흘러든다 → 교체 저장.
    import datetime as dt

    from app.data.pykrx_client import PrefetchBundle
    from app.store import final_cache
    from app.store.models import FinalPrefetch

    run_date = dt.date(2026, 7, 13)
    stale = PrefetchBundle(
        run_date=run_date, universe=["000001"], h_ref_252={}, h_ref_60={"000001": 10.0},
        atr20={"000001": 1.0}, avg_value_20d={"000001": 1e10},
        net_purchases={}, index_ma5={})           # 수급 결손(잘못된 D-1)
    final_cache.persist_prefetch_bundle(session, stale)
    session.commit()

    fresh = PrefetchBundle(
        run_date=run_date, universe=["000660"], h_ref_252={}, h_ref_60={"000660": 20.0},
        atr20={"000660": 2.0}, avg_value_20d={"000660": 5e10},
        net_purchases={"000660": 8e9}, index_ma5={})
    final_cache.persist_prefetch_bundle(session, fresh)
    session.commit()

    rows = session.query(FinalPrefetch).filter(FinalPrefetch.run_date == run_date).all()
    assert [r.ticker for r in rows] == ["000660"]      # 옛 행 잔존 금지
    assert rows[0].d1_supply_value == 8e9


def test_persist_prefetch_bundle_roundtrips_listing_days(session):
    # off-by-2: 실이력행수가 FinalPrefetch 로 저장되고 load_prefetch 로 복원돼야
    # 15:20 후보 구성 시 52주 신고가 축(≥252) 판정에 쓰인다.
    import datetime as dt

    from app.data.pykrx_client import PrefetchBundle
    from app.store import final_cache

    run_date = dt.date(2026, 7, 14)
    bundle = PrefetchBundle(
        run_date=run_date, universe=["LONG", "SHORT"],
        h_ref_252={"LONG": 120.0}, h_ref_60={"LONG": 100.0, "SHORT": 90.0},
        atr20={"LONG": 1.0, "SHORT": 1.0},
        avg_value_20d={"LONG": 1e10, "SHORT": 1e10},
        net_purchases={}, index_ma5={},
        listing_days={"LONG": 260, "SHORT": 150})
    final_cache.persist_prefetch_bundle(session, bundle)
    session.commit()

    loaded = final_cache.load_prefetch(session, run_date)
    assert loaded["LONG"].listing_days == 260
    assert loaded["SHORT"].listing_days == 150
    assert loaded["LONG"].h_ref_252 == 120.0


def test_persist_universe_cache_replaces_prior_rows_for_same_date(session):
    # 재실행(유니버스 변경) 시 옛 as_of 행이 남으면 /universe 스캐너가 신·구 합집합으로
    # 부풀어 관측을 오염한다(2026-07-13 358행 사고). delete-then-insert 로 교체.
    import datetime as dt
    from types import SimpleNamespace

    from app.store import final_cache
    from app.store.models import UniverseCache

    as_of = dt.date(2026, 7, 13)
    first = SimpleNamespace(run_date=as_of, universe=["A", "B", "C"],
                            market_of={"A": "KOSPI", "B": "KOSPI", "C": "KOSDAQ"},
                            avg_value_20d={"A": 1e10, "B": 1e10, "C": 1e10})
    final_cache.persist_universe_cache(session, first, names={})
    session.commit()
    second = SimpleNamespace(run_date=as_of, universe=["A", "D"],
                             market_of={"A": "KOSPI", "D": "KOSDAQ"},
                             avg_value_20d={"A": 1e10, "D": 1e10})
    final_cache.persist_universe_cache(session, second, names={})
    session.commit()

    rows = session.query(UniverseCache).filter(UniverseCache.as_of == as_of).all()
    assert sorted(r.ticker for r in rows) == ["A", "D"]     # 옛 B,C 잔존 금지(누적 없음)
