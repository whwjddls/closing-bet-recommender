# backend/tests/engine/test_pipeline.py
import pytest

from app.engine.pipeline import (
    StaticCandidate,
    LiveQuote,
    run_pipeline,
)


def _cand(ticker, market="KOSDAQ", **kw):
    base = dict(
        ticker=ticker, name=f"N{ticker}", market=market, sec_type="COMMON",
        avg_value_20d=50_000_000_000, is_managed=False, is_warning=False,
        is_caution=False, listing_days=300, high_60=23500.0, high_252=24000.0,
        prev_high=24800.0, atr20=300.0, d1_supply_value=8_000_000_000.0,
        d1_value=50_000_000_000.0,
    )
    base.update(kw)
    return StaticCandidate(**base)


def _quote(p_now=24500.0, cum=2500.0, chg=3.0, lu=False, vi=False, halt=False):
    return LiveQuote(
        p_now=p_now, cum_volume_1520=cum, day_change_pct=chg,
        is_limit_up=lu, is_vi=vi, is_halted=halt,
    )


def _live(mapping):
    def _fetch(tickers):
        return {t: mapping[t] for t in tickers if t in mapping}
    return _fetch


def test_worked_example_kosdaq_a_end_to_end():
    cands = [_cand("000660")]
    res = run_pipeline(
        candidates=cands,
        fetch_live=_live({"000660": _quote()}),
        regime_by_market={"KOSDAQ": 1.0},
        modeled_avg_by_ticker={"000660": 1000.0},   # RVOL=2500/1000=2.5
        veto_by_ticker={"000660": 1},
    )
    assert res.published is True and res.reason == "OK"
    row = res.rows[0]
    assert row.rank == 1
    assert row.s_shin == pytest.approx(1.164096, abs=1e-4)
    assert row.rvol_confirm == pytest.approx(0.933618, abs=1e-5)
    assert row.supply_tilt == pytest.approx(1.032, abs=1e-4)
    assert row.core == pytest.approx(1.122, abs=1e-3)
    assert row.final == pytest.approx(1.122, abs=1e-3)
    assert row.grade == "S"
    assert row.buy_price_provisional == 24500.0 and row.provisional_flag is True


def test_static_hygiene_filters_before_live_fetch():
    requested = []

    def _fetch(tickers):
        requested.extend(tickers)
        return {t: _quote() for t in tickers}

    cands = [_cand("000660"), _cand("ETF01", sec_type="ETF")]
    run_pipeline(cands, _fetch, {"KOSDAQ": 1.0}, {"000660": 1000.0}, {"000660": 1})
    assert "ETF01" not in requested   # 라이브 조회 전 정적위생 제거(레이트버짓 보호)


def test_dynamic_hygiene_drops_overheated():
    cands = [_cand("000660")]
    res = run_pipeline(
        cands, _live({"000660": _quote(chg=25.0)}),
        {"KOSDAQ": 1.0}, {"000660": 1000.0}, {"000660": 1},
    )
    assert res.reason == "RISK_OFF" and res.rows == []   # 과열 제거 → 보드 비음


def test_emit_only_final_positive_and_veto_blocks():
    cands = [_cand("000660"), _cand("111111")]
    res = run_pipeline(
        cands, _live({"000660": _quote(), "111111": _quote()}),
        {"KOSDAQ": 1.0},
        {"000660": 1000.0, "111111": 1000.0},
        {"000660": 1, "111111": 0},   # 111111 veto → final=0 제외
    )
    assert [r.ticker for r in res.rows] == ["000660"]


def test_tie_break_by_d1_value():
    # 동일 final → D-1 거래대금 큰 종목 우선
    a = _cand("AAAAAA", d1_value=10_000_000_000.0)
    b = _cand("BBBBBB", d1_value=90_000_000_000.0)
    res = run_pipeline(
        [a, b],
        _live({"AAAAAA": _quote(), "BBBBBB": _quote()}),
        {"KOSDAQ": 1.0},
        {"AAAAAA": 1000.0, "BBBBBB": 1000.0},
        {"AAAAAA": 1, "BBBBBB": 1},
    )
    assert res.rows[0].final == pytest.approx(res.rows[1].final)
    assert [r.ticker for r in res.rows] == ["BBBBBB", "AAAAAA"]
    assert [r.rank for r in res.rows] == [1, 2]


def test_low_regime_yields_empty_board_published():
    res = run_pipeline(
        [_cand("000660")], _live({"000660": _quote()}),
        {"KOSDAQ": 0.0}, {"000660": 1000.0}, {"000660": 1},
    )
    assert res.published is True and res.reason == "RISK_OFF" and res.rows == []


def test_mixed_market_regime_no_cross_contamination():
    # KOSPI regime 0.0 → KOSPI 종목 final=0 제외, KOSDAQ regime 1.0 → 발행. 교차오염 없음.
    kospi = _cand("KSPI01", market="KOSPI")
    kosdaq = _cand("KSDQ01", market="KOSDAQ")
    res = run_pipeline(
        [kospi, kosdaq],
        _live({"KSPI01": _quote(), "KSDQ01": _quote()}),
        {"KOSPI": 0.0, "KOSDAQ": 1.0},
        {"KSPI01": 1000.0, "KSDQ01": 1000.0},
        {"KSPI01": 1, "KSDQ01": 1},
    )
    assert [r.ticker for r in res.rows] == ["KSDQ01"]
    assert res.rows[0].market == "KOSDAQ"
    assert res.rows[0].regime_mult == 1.0


def test_empty_universe_after_static_hygiene():
    res = run_pipeline(
        [_cand("ETF01", sec_type="ETF")], _live({}),
        {"KOSDAQ": 1.0}, {}, {},
    )
    assert res.reason == "EMPTY_UNIVERSE" and res.published is True


def test_low_coverage_fail_closed_unpublished():
    cands = [_cand(f"{i:06d}") for i in range(10)]
    res = run_pipeline(
        cands, _live({"000000": _quote()}),   # 1/10 = 10% < 70%
        {"KOSDAQ": 1.0},
        {c.ticker: 1000.0 for c in cands},
        {c.ticker: 1 for c in cands},
    )
    assert res.published is False and res.reason == "LOW_COVERAGE"


def test_no_data_unpublished():
    cands = [_cand("000660")]
    res = run_pipeline(cands, _live({}), {"KOSDAQ": 1.0}, {"000660": 1000.0}, {"000660": 1})
    assert res.published is False and res.reason == "NO_DATA"


def test_emit_caps_at_max_emit():
    cands = [_cand(f"{i:06d}") for i in range(40)]
    quotes = {c.ticker: _quote() for c in cands}
    res = run_pipeline(
        cands, _live(quotes), {"KOSDAQ": 1.0},
        {c.ticker: 1000.0 for c in cands},
        {c.ticker: 1 for c in cands},
        max_emit=30,
    )
    assert len(res.rows) == 30


# ── 퍼널 계측: 빈 보드의 원인을 단계별 생존 수로 남긴다 ────────────────────
def test_funnel_counts_survivors_at_each_stage():
    # 3종목: A=정상발행, B=돌파미달(s_신=0), C=공시veto
    cands = [_cand("A", market="KOSPI", high_60=100.0, high_252=100.0),
             _cand("B", market="KOSPI", high_60=100.0, high_252=100.0),
             _cand("C", market="KOSPI", high_60=100.0, high_252=100.0)]
    quotes = {"A": _quote(p_now=100.0), "B": _quote(p_now=50.0),   # B: near=0.5 → s_신=0
              "C": _quote(p_now=100.0)}
    res = run_pipeline(cands, lambda ts: quotes, {"KOSPI": 1.0},
                       {t: None for t in "ABC"},
                       {"A": 1, "B": 1, "C": 0})                   # C: veto 차단
    f = res.funnel
    assert f.candidates == 3 and f.static_ok == 3 and f.quotes == 3
    assert f.dynamic_ok == 3
    assert f.shin_zero == 1                                        # B
    assert f.veto_blocked == 1                                     # C
    assert f.regime_zero == 0
    assert f.emitted == 1 and f.published == 1                     # A만 발행
    assert [r.ticker for r in res.rows] == ["A"]


def test_emit_floors_at_grade_a_drops_b_c():
    # A 이상(S·A)만 발행 — B·C 는 실적중률이 낮아 등급 하한(core>=0.6)에서 제외되고
    # funnel.grade_dropped 로 계측된다. 등급은 core(레짐 독립) 기준.
    cands = [
        _cand("AA", high_60=100.0, high_252=None, listing_days=150, d1_supply_value=0.0),
        _cand("BB", high_60=100.0, high_252=None, listing_days=150, d1_supply_value=0.0),
    ]
    quotes = {"AA": _quote(p_now=100.0),    # near60=1.0 → core≈1.0 → S
              "BB": _quote(p_now=95.0)}     # near60=0.95 → core≈0.5 → B
    res = run_pipeline(cands, lambda ts: quotes, {"KOSDAQ": 1.0},
                       {"AA": None, "BB": None}, {"AA": 1, "BB": 1})
    assert [r.ticker for r in res.rows] == ["AA"]      # B 제외, A 이상만
    assert res.rows[0].grade in ("S", "A")
    assert res.funnel.grade_dropped == 1               # BB(B등급) 계측
    assert res.funnel.emitted == 1


def test_funnel_marks_risk_off_when_regime_zero_kills_all():
    cands = [_cand("A", market="KOSPI", high_60=100.0, high_252=100.0)]
    res = run_pipeline(cands, lambda ts: {"A": _quote(p_now=100.0)},
                       {"KOSPI": 0.0},                             # 리스크오프
                       {"A": None}, {"A": 1})
    assert res.reason == "RISK_OFF" and res.rows == []
    assert res.funnel.regime_zero == 1 and res.funnel.emitted == 0
    assert res.funnel.shin_zero == 0                               # 돌파는 정상 — 시장이 죽인 것


def test_funnel_records_static_hygiene_wipeout():
    cands = [_cand("A", market="KOSPI", avg_value_20d=1.0)]                        # 유동성 바닥 미달
    res = run_pipeline(cands, lambda ts: {}, {"KOSPI": 1.0}, {}, {})
    assert res.reason == "EMPTY_UNIVERSE"
    assert res.funnel.candidates == 1 and res.funnel.static_ok == 0


# ── US-004: 유니버스 확대(600) 시 파이프라인 회귀 없음 ──────────────
def test_pipeline_scales_to_expanded_universe():
    # 확대(N=600)에서도 정상 발행 — 커버리지 정확, MAX_EMIT(30) 상한 유지, 랭킹 내림차순.
    n = 600
    cands = [_cand(f"{i:06d}", high_60=23500.0 + i) for i in range(n)]   # 돌파 강도 차등
    quotes = {f"{i:06d}": _quote() for i in range(n)}
    res = run_pipeline(
        candidates=cands, fetch_live=_live(quotes),
        regime_by_market={"KOSDAQ": 1.0},
        modeled_avg_by_ticker={f"{i:06d}": 1000.0 for i in range(n)},
        veto_by_ticker={f"{i:06d}": 1 for i in range(n)},
    )
    assert res.published is True and res.reason == "OK"
    assert res.coverage_pct == pytest.approx(1.0)          # 커버리지 회귀 없음
    assert res.funnel.candidates == n and res.funnel.static_ok == n
    assert len(res.rows) == 30                              # 확대해도 발행 상한 유지
    finals = [r.final for r in res.rows]
    assert finals == sorted(finals, reverse=True)          # final 내림차순 랭킹


def test_pipeline_expanded_universe_partial_coverage_still_publishes():
    # 확대 시 꼬리 종목 일부가 시세 실패해도 커버리지가 임계(0.70) 이상이면 보드 전체가
    # LOW_COVERAGE 로 막히지 않는다 — 확대 도입의 커버리지 회귀 가드.
    n = 500
    cands = [_cand(f"{i:06d}") for i in range(n)]
    quotes = {f"{i:06d}": _quote() for i in range(400)}    # 400/500 = 0.80 ≥ 0.70
    res = run_pipeline(
        candidates=cands, fetch_live=_live(quotes),
        regime_by_market={"KOSDAQ": 1.0},
        modeled_avg_by_ticker={f"{i:06d}": 1000.0 for i in range(n)},
        veto_by_ticker={f"{i:06d}": 1 for i in range(n)},
    )
    assert res.published is True and res.reason == "OK"
    assert res.coverage_pct == pytest.approx(0.80)
    assert len(res.rows) == 30
