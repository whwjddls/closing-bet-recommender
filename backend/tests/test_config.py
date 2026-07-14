from app import __version__
from app.config import get_settings, recommendations_json_path


def test_version_is_exposed():
    assert __version__ == "0.1.0"


def test_settings_default_paths_resolve():
    settings = get_settings()
    assert settings.state_dir.name == "state"
    assert settings.db_path.suffix in {".sqlite", ".db"}


def test_recommendations_json_path_uses_date_filename(tmp_path):
    path = recommendations_json_path(tmp_path, "2026-06-30")
    assert path.parts[-2:] == ("recommendations", "2026-06-30.json")


def test_settings_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("CBR_STATE_DIR", str(tmp_path / "custom_state"))
    settings = get_settings()
    assert settings.state_dir == (tmp_path / "custom_state")


# ── EXE(PyInstaller) 경로 해소 — .env·DB 가 임시폴더로 새지 않아야 한다 ──────
def test_app_root_uses_backend_dir_when_not_frozen():
    from app.config import _app_root

    assert (_app_root() / "app" / "config.py").exists()      # 개발 실행 = backend/


def test_app_root_prefers_sibling_backend_when_frozen(tmp_path, monkeypatch):
    # 레포 안에 EXE 를 둔 경우 — 옆 backend/ 의 기존 .env·state 를 그대로 이어받는다.
    import sys

    from app import config

    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".env").write_text("KIS_APP_KEY=x", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "종가베팅.exe"))
    assert config._app_root() == backend


def test_app_root_uses_exe_dir_when_frozen_standalone(tmp_path, monkeypatch):
    # backend/ 가 없는 단독 배포 — EXE 옆을 기준으로 삼는다(임시폴더 금지).
    import sys

    from app import config

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "종가베팅.exe"))
    assert config._app_root() == tmp_path
