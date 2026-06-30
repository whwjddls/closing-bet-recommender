from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, recommendations, stock


def create_app() -> FastAPI:
    app = FastAPI(title="closing-bet-recommender", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(recommendations.router)
    app.include_router(stock.router)
    return app


app = create_app()
