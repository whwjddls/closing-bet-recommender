from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    backtest, calendar, disclosures, health, market, performance, recommendations,
    stock, universe,
)
from app.store.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # 스타트업 스키마 보장(멱등) — init_db 데드코드/미호출 회귀 방지
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="closing-bet-recommender", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(recommendations.router)
    app.include_router(stock.router)
    app.include_router(performance.router)
    app.include_router(universe.router)
    app.include_router(backtest.router)
    app.include_router(market.router)
    app.include_router(calendar.router)
    app.include_router(disclosures.router)
    return app


app = create_app()
