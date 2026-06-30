from datetime import date, datetime

from app.engine.orchestrator import (
    orchestrate_run,
    RunResult,
    RecRow,
    RegimeInfo,
    compute_modeled_avg,
)


class FakeAdapter:
    def d1_value_top(self, run_date, n):
        return ["000660", "005930"]                                  # D-1 거래대금 상위(혼합시장)

    def live_value_top(self, market, top):
        return ["111111"] if market == "KOSDAQ" else ["005930"]

    def market_of(self, t):
        return {"000660": "KOSDAQ", "005930": "KOSPI", "111111": "KOSDAQ"}[t]

    def static_ok(self, t):
        return True

    def quote(self, t):
        return type("Q", (), {"ticker": t, "price": 100.0, "cum_volume": 1000, "cum_value": 1.0e8,
                              "change_pct": 1.0, "is_halted": False, "is_limit_up": False, "is_vi": False})()

    def regime_inputs(self, market):  # (index_level, prev5_closes) → compute_regime
        # 둘 다 UP 레짐(regime_mult=1.0): KOSPI 005930 이 레짐 게이트를 통과해야 한다.
        return ((350.0, [349, 348, 347, 346, 345]) if market == "KOSDAQ"
                else (2700.0, [2650, 2655, 2660, 2665, 2670]))

    def net_purchase(self, t):
        return 0.0

    def avg_value_20d(self, t):
        return 5.0e8

    def veto(self, t, snapshot_at):
        return 0 if t == "000660" else 1                             # 000660 희석 veto


class DictStore:                                                     # 인메모리 store 페이크
    def __init__(self):
        self.vol = []
        self.regimes = []

    def upsert_volume_snapshot(self, ticker, d, cum_volume, cum_value):
        self.vol.append((ticker, d, cum_value))

    def trailing_volume(self, ticker, before):
        return [v for (tk, _, v) in self.vol if tk == ticker]

    def save_regime(self, run_date, market, info):
        self.regimes.append((market, info))


def fake_run_pipeline(candidates, fetch_live, regime_by_market, modeled_avg_by_ticker, veto_by_ticker, max_emit):
    rows = []
    for t in candidates:
        if veto_by_ticker.get(t, 1) == 0:
            continue                                                 # veto 탈락
        rm = regime_by_market[FakeAdapter().market_of(t)]
        if rm == 0.0:
            continue                                                 # 레짐 게이트
        rows.append(type("E", (), {"ticker": t, "name": "N", "market": FakeAdapter().market_of(t),
            "price": 100.0, "buy": 100.0, "s_shin": 1.0, "s_geo": 0.8, "rvol_confirm": 0.9, "supply_tilt": 1.0,
            "regime_mult": rm, "veto": 1, "core": 0.9, "final": 0.9 * rm, "grade": "A", "near_252": 1.0,
            "near_60": 1.0, "rvol": 2.0, "target": 103.0, "stop": 97.0, "spark": [1, 2, 3], "base_flag": False})())
    return type("PR", (), {"published": bool(rows), "reason": None, "rows": rows, "coverage_pct": 1.0})()


def test_orchestrate_pool_regime_coverage():
    res = orchestrate_run(date(2026, 6, 30), datetime(2026, 6, 30, 15, 20),
                          adapter=FakeAdapter(), store=DictStore(), run_pipeline_fn=fake_run_pipeline)
    assert isinstance(res, RunResult) and res.data_available is True
    emitted = {r.ticker for r in res.recommendations}
    assert "005930" in emitted and "000660" not in emitted           # 풀 union + veto 탈락
    assert res.kis_coverage_pct == 100.0                             # 0~1 ×100
    assert set(res.regimes) == {"KOSPI", "KOSDAQ"}                   # 시장별 RegimeInfo
    assert all(isinstance(r, RecRow) for r in res.recommendations)   # EngineRow→RecRow


def test_modeled_rvol_threshold():
    assert compute_modeled_avg([1.0e8] * 19, min_sessions=20) is None     # <20세션 → 중립
    assert compute_modeled_avg([1.0e8] * 20, min_sessions=20) == 1.0e8    # ≥20세션 → 평균
