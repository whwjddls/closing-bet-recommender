from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


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
