from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# backend/.env 를 os.environ 에 주입(파일 없으면 조용히 무시) — KIS/DART 키 등. 임포트보다 먼저.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.api import (  # noqa: E402  (env 주입 후 임포트)
    backtest, calendar, disclosures, health, highs, jobs, market, news, performance,
    recommendations, reminder, run, stock, universe,
)
from app.store.db import init_db  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()          # 스타트업 스키마 보장(멱등) — init_db 데드코드/미호출 회귀 방지
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="closing-bet-recommender", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(recommendations.router)
    app.include_router(stock.router)
    app.include_router(performance.router)
    app.include_router(reminder.router)
    app.include_router(universe.router)
    app.include_router(backtest.router)
    app.include_router(market.router)
    app.include_router(calendar.router)
    app.include_router(disclosures.router)
    app.include_router(highs.router)
    app.include_router(run.router)
    app.include_router(news.router)
    app.include_router(jobs.router)
    return app


app = create_app()
