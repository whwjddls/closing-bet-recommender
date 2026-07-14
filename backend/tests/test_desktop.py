import pytest
from fastapi.testclient import TestClient

from app.desktop import create_desktop_app, frontend_dist_path


@pytest.fixture
def dist(tmp_path, monkeypatch):
    """가짜 프론트 dist — 번들 경로 해소와 SPA 폴백을 네트워크 없이 검증."""
    (tmp_path / "index.html").write_text("<html>board</html>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    monkeypatch.setenv("CBR_FRONTEND_DIST", str(tmp_path))
    return tmp_path


def test_frontend_dist_path_uses_env_override(dist):
    assert frontend_dist_path() == dist


def test_frontend_dist_path_none_when_index_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CBR_FRONTEND_DIST", str(tmp_path))   # index.html 없음
    assert frontend_dist_path() is None


def test_serves_spa_at_root(dist):
    client = TestClient(create_desktop_app())
    resp = client.get("/")
    assert resp.status_code == 200
    assert "board" in resp.text


def test_serves_static_assets(dist):
    client = TestClient(create_desktop_app())
    assert client.get("/assets/app.js").status_code == 200


def test_api_lives_under_api_prefix(dist):
    # SPA 라우트(/stock/:code, /performance)가 API 경로와 충돌하므로 API 는 /api 아래.
    client = TestClient(create_desktop_app())
    assert client.get("/api/health").status_code == 200


def test_spa_route_is_not_shadowed_by_api_route(dist):
    # /stock/005930 은 SPA 딥링크여야 한다 — API JSON 이 나오면 화면이 깨진다.
    client = TestClient(create_desktop_app())
    resp = client.get("/stock/005930")
    assert resp.status_code == 200
    assert "board" in resp.text                     # index.html 폴백
    assert "application/json" not in resp.headers.get("content-type", "")


def test_deep_link_falls_back_to_index(dist):
    # 폰에서 링크로 진입 후 새로고침해도 화면이 살아야 한다.
    client = TestClient(create_desktop_app())
    assert "board" in client.get("/performance").text


def test_falls_back_to_api_only_when_dist_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("CBR_FRONTEND_DIST", str(tmp_path / "nope"))
    client = TestClient(create_desktop_app())
    assert client.get("/health").status_code == 200      # dist 없으면 루트 API(개발 폴백)
