import datetime as dt

import pytest

from app.store.snapshots import write_snapshot, read_snapshot, snapshot_path

RUN_DATE = dt.date(2026, 6, 30)


@pytest.fixture
def snap_state(monkeypatch, tmp_path):
    # 00 §1 계약: write_snapshot(run_date, payload) 2-인자.
    # state_dir은 파라미터가 아니라 config(CBR_STATE_DIR)에서 해석 → 테스트 격리는 env override로.
    monkeypatch.setenv("CBR_STATE_DIR", str(tmp_path))
    return tmp_path


def test_snapshot_path_layout(snap_state):
    p = snapshot_path(RUN_DATE)
    assert p.parent.name == "recommendations"
    assert p.name == "2026-06-30.json"


def test_write_returns_path_string(snap_state):
    # 00 §1: write_snapshot(...) -> str (경로 반환)
    returned = write_snapshot(RUN_DATE, {"a": 1})
    assert isinstance(returned, str)
    assert returned == str(snapshot_path(RUN_DATE))


def test_write_then_read_roundtrip_keeps_provisional_and_final(snap_state):
    payload = {
        "run_date": "2026-06-30",
        "session_type": "정규",
        "recommendations": [
            {
                "ticker": "000660", "name": "SK하이닉스", "grade": "S",
                "price_provisional": 24500,
                "buy_price_provisional": 24500,
                "buy_price_final": None,        # 잠정-확정 갭: 익일 확정 전 None
                "provisional_flag": 1,
            }
        ],
    }
    write_snapshot(RUN_DATE, payload)
    got = read_snapshot(RUN_DATE)
    assert got == payload
    # 한글 비-ascii 보존
    assert got["recommendations"][0]["name"] == "SK하이닉스"


def test_read_missing_returns_none(snap_state):
    assert read_snapshot(dt.date(2099, 1, 1)) is None


def test_write_is_atomic_no_tmp_leftover(snap_state):
    write_snapshot(RUN_DATE, {"a": 1})
    recs_dir = snapshot_path(RUN_DATE).parent
    leftovers = [p for p in recs_dir.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []


def test_overwrite_replaces_content(snap_state):
    write_snapshot(RUN_DATE, {"v": 1})
    write_snapshot(RUN_DATE, {"v": 2})
    assert read_snapshot(RUN_DATE) == {"v": 2}
