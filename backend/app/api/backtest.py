from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import BacktestResponse

router = APIRouter(tags=["backtest"])


def get_backtest_runner() -> Callable:
    """프로덕션 백테스트 러너 — run_backtest 에 pykrx 기반 패널 로더를 바인딩(계약 §4).

    로더 무주입 시 run_backtest 가 fail-fast(ValueError→500) 하므로 기본 러너에서
    ``load_price_panel``/``load_vwap_panel`` 을 반드시 바인딩한다. membership 소스는
    프로덕션 미확보 → survivorship 파생 False → acceptance DOWNSCOPE(조용한 통과 금지)."""
    from app.backtest.engine import run_backtest
    from app.backtest.loaders import load_price_panel, load_vwap_panel

    def _runner(start: date, end: date):
        return run_backtest(start, end, load_price_panel=load_price_panel,
                            load_vwap_panel=load_vwap_panel)

    return _runner


@router.get("/backtest", response_model=BacktestResponse)
def get_backtest(start: date, end: date, runner: Callable = Depends(get_backtest_runner)) -> BacktestResponse:
    res = runner(start, end)
    return BacktestResponse(
        start=res.start, end=res.end, n_picks=res.n_picks, rank_ic=res.rank_ic,
        t_stat=res.t_stat, hit_rate=res.hit_rate, avg_return=res.avg_return, note=res.note,
    )
