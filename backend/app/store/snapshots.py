from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.config import get_settings, recommendations_json_path


def _date_str(run_date: dt.date | str) -> str:
    if isinstance(run_date, dt.date):  # datetime은 date의 서브클래스 → 함께 처리
        return run_date.strftime("%Y-%m-%d")
    return str(run_date)


def snapshot_path(run_date: dt.date | str) -> Path:
    """state/recommendations/YYYY-MM-DD.json 경로. state_dir은 config(00 §1)에서 해석."""
    return recommendations_json_path(get_settings().state_dir, _date_str(run_date))


def write_snapshot(run_date: dt.date | str, payload: Any) -> str:
    """state/recommendations/YYYY-MM-DD.json 저장, 경로 반환. (2-인자 — 00 §1 / 04 시그니처)"""
    path = snapshot_path(run_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_name, path)  # atomic rename
    except BaseException:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)
        raise
    return str(path)


def read_snapshot(run_date: dt.date | str) -> Any | None:
    path = snapshot_path(run_date)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
