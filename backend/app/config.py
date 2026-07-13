from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _BACKEND_ROOT / ".env"


def load_env() -> None:
    """``backend/.env`` 를 os.environ 에 주입(파일 없으면 조용히 무시, 멱등).

    웹서버(main.py)와 **스케줄러 엔트리포인트가 각각** 호출해야 한다 —
    ``python -m app.scheduler.daily_run`` 은 main.py 를 임포트하지 않으므로 여기서
    로드하지 않으면 KIS/DART 크리덴셜이 비어 fail-closed 로 죽는다."""
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH)


@dataclass(slots=True, frozen=True)
class Settings:
    state_dir: Path
    db_path: Path


def get_settings() -> Settings:
    state_dir = Path(os.environ.get("CBR_STATE_DIR", _BACKEND_ROOT / "state"))
    db_path = Path(os.environ.get("CBR_DB_PATH", state_dir / "cbr.sqlite"))
    return Settings(state_dir=state_dir, db_path=db_path)


def recommendations_json_path(state_dir, run_date: str) -> Path:
    return Path(state_dir) / "recommendations" / f"{run_date}.json"
