from datetime import date
from typing import Callable

from fastapi import APIRouter, Depends

from app.api.schemas import BacktestResponse

router = APIRouter(tags=["backtest"])


def get_backtest_runner() -> Callable:
    """서브시스템 3의 백테스트 러너를 지연 임포트로 주입(테스트는 override)."""
    from app.backtest.engine import run_backtest
    return run_backtest


@router.get("/backtest", response_model=BacktestResponse)
def get_backtest(start: date, end: date, runner: Callable = Depends(get_backtest_runner)) -> BacktestResponse:
    res = runner(start, end)
    return BacktestResponse(
        start=res.start, end=res.end, n_picks=res.n_picks, rank_ic=res.rank_ic,
        t_stat=res.t_stat, hit_rate=res.hit_rate, avg_return=res.avg_return, note=res.note,
    )
