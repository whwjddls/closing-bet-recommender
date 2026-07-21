from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


def _app_root() -> Path:
    """.env·state 의 기준 디렉터리.

    PyInstaller onefile 로 얼리면 ``__file__`` 이 **임시 추출 폴더**(_MEIPASS)를 가리켜,
    그대로 두면 .env 를 못 찾고 DB 가 매 실행마다 임시폴더에 새로 생겼다가 사라진다.
    얼린 경우엔 EXE 위치를 기준으로 삼되, 레포 안에 둔 EXE(개발 레이아웃)는 옆의
    ``backend/`` 를 그대로 쓰게 해 기존 .env·DB 를 이어받는다."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        sibling_backend = exe_dir / "backend"
        return sibling_backend if (sibling_backend / ".env").exists() else exe_dir
    return Path(__file__).resolve().parent.parent


_BACKEND_ROOT = _app_root()
ENV_PATH = _BACKEND_ROOT / ".env"


def load_env() -> None:
    """``backend/.env`` 를 os.environ 에 주입(파일 없으면 조용히 무시, 멱등).

    웹서버(main.py)와 **스케줄러 엔트리포인트가 각각** 호출해야 한다 —
    ``python -m app.scheduler.daily_run`` 은 main.py 를 임포트하지 않으므로 여기서
    로드하지 않으면 KIS/DART 크리덴셜이 비어 fail-closed 로 죽는다."""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)


DEFAULT_UNIVERSE_N = 200   # D-1 거래대금 상위 유니버스 기본 크기(CBR_UNIVERSE_N 로 조정)


def _env_int(name: str, default: int) -> int:
    """env 정수 파싱 — 미설정/공백/비정수는 default 로 폴백(fail-soft, 배치 중단 방지)."""
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(slots=True, frozen=True)
class Settings:
    state_dir: Path
    db_path: Path
    universe_n: int


def get_settings() -> Settings:
    state_dir = Path(os.environ.get("CBR_STATE_DIR", _BACKEND_ROOT / "state"))
    db_path = Path(os.environ.get("CBR_DB_PATH", state_dir / "cbr.sqlite"))
    universe_n = _env_int("CBR_UNIVERSE_N", DEFAULT_UNIVERSE_N)
    return Settings(state_dir=state_dir, db_path=db_path, universe_n=universe_n)


def recommendations_json_path(state_dir, run_date: str) -> Path:
    return Path(state_dir) / "recommendations" / f"{run_date}.json"
