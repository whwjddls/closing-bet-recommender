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
