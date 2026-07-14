"""데스크톱(EXE) 앱 — 정적 프론트 + API 를 한 오리진에서 서빙.

개발용 ``create_app()`` 은 라우터를 루트에 단다(/health, /stock/{code} …). 그런데 SPA
라우트(``/stock/:code``, ``/performance``)가 그 경로와 **정확히 충돌**하므로, 한 오리진에
합칠 때는 API 를 ``/api`` 아래로 내리고 루트는 SPA 가 가져야 한다. 프론트는
``VITE_API_BASE=/api`` 로 빌드한다.

SPA 딥링크(/stock/005930 직접 진입)는 그런 파일이 없어 404 가 되므로 index.html 로
폴백한다 — 이게 없으면 폰에서 링크를 눌러 들어온 뒤 새로고침하면 화면이 깨진다.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import FileResponse

from app.main import create_app

logger = logging.getLogger(__name__)

FRONTEND_DIST_ENV = "CBR_FRONTEND_DIST"
BUNDLED_DIST_NAME = "frontend_dist"     # PyInstaller --add-data 목적지명


def frontend_dist_path() -> Path | None:
    """정적 프론트(dist) 위치. env → PyInstaller 번들 → 레포 경로 순. 없으면 None."""
    override = os.environ.get(FRONTEND_DIST_ENV)
    if override:
        path = Path(override)
        return path if (path / "index.html").exists() else None

    bundled = getattr(sys, "_MEIPASS", None)        # PyInstaller onefile 임시 추출 경로
    candidates = []
    if bundled:
        candidates.append(Path(bundled) / BUNDLED_DIST_NAME)
    repo_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    candidates.append(repo_dist)

    for path in candidates:
        if (path / "index.html").exists():
            return path
    return None


class SpaStaticFiles(StaticFiles):
    """정적 파일 서빙 + SPA 폴백 — 없는 경로는 index.html 로(클라이언트 라우팅).

    StaticFiles 는 파일이 없으면 404 **예외를 던진다**(응답 반환이 아니다) — 상태코드만
    보면 폴백이 걸리지 않아 딥링크가 JSON 404 로 깨진다."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return self._index()
            raise
        if response.status_code == 404:
            return self._index()
        return response

    def _index(self) -> FileResponse:
        return FileResponse(Path(self.directory) / "index.html")


def create_desktop_app() -> FastAPI:
    """루트=SPA, /api=백엔드. dist 가 없으면 API 만 노출한다(개발 폴백)."""
    api = create_app()
    dist = frontend_dist_path()
    if dist is None:
        logger.warning("프론트 dist 없음 — API 만 노출한다(먼저 `npm run build` 필요)")
        return api

    app = FastAPI(title="closing-bet-recommender (desktop)")
    app.mount("/api", api)
    app.mount("/", SpaStaticFiles(directory=str(dist), html=True), name="spa")
    return app
