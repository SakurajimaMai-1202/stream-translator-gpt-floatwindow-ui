import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from backend.core.admin_auth import DEV_ORIGIN_REGEX, register_admin_auth


TOKEN = "test-admin-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FLOATWINDOW_ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=DEV_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_admin_auth(app, "/api")

    @app.api_route("/api/private", methods=["GET", "POST"])
    async def private():
        return {"ok": True}

    @app.api_route("/api/health", methods=["GET", "POST"])
    async def health():
        return {"status": "ok"}

    @app.get("/assets/test.js")
    async def static_asset():
        return {"static": True}

    @app.get("/")
    async def index():
        return {"index": True}

    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.parametrize("method", ["get", "post"])
@pytest.mark.parametrize("headers", [{}, {"X-FloatWindow-Token": "wrong-token"}])
def test_admin_api_rejects_missing_or_wrong_token(client, method, headers):
    response = getattr(client, method)("/api/private", headers=headers)
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")


def test_admin_api_accepts_header(client):
    assert client.get("/api/private", headers={"X-FloatWindow-Token": TOKEN}).status_code == 200


def test_admin_api_accepts_cookie(client):
    client.cookies.set("fw_admin_token", TOKEN)
    assert client.get("/api/private").status_code == 200


def test_admin_api_rejects_wrong_cookie(client):
    client.cookies.set("fw_admin_token", "wrong-token")
    assert client.get("/api/private").status_code == 401


def test_valid_cookie_accepts_request_with_wrong_header(client):
    client.cookies.set("fw_admin_token", TOKEN)
    assert client.get("/api/private", headers={"X-FloatWindow-Token": "wrong-token"}).status_code == 200


def test_query_token_does_not_authenticate_other_api(client):
    assert client.get("/api/private", params={"token": TOKEN}).status_code == 401


def test_api_options_never_reaches_handler(client):
    # OPTIONS 交給 CORS 處理，不會執行任何路由
    assert client.options("/api/private").status_code == 405
    preflight = client.options("/api/private", headers={
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-floatwindow-token",
    })
    assert preflight.status_code == 200
    evil = client.options("/api/private", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "POST",
    })
    assert "access-control-allow-origin" not in evil.headers


def test_health_only_exempts_get(client):
    assert client.get("/api/health").status_code == 200
    assert client.post("/api/health").status_code == 401


def test_static_paths_remain_accessible(client):
    assert client.get("/").status_code == 200
    assert client.get("/assets/test.js").status_code == 200


def test_auth_disabled_without_environment_token(client, monkeypatch):
    monkeypatch.delenv("FLOATWINDOW_ADMIN_TOKEN", raising=False)
    assert client.post("/api/private").status_code == 200


def test_auth_session_sets_strict_http_only_cookie(client):
    response = client.get("/api/auth/session", params={"token": TOKEN}, follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"] == "/"
    cookie = response.headers["set-cookie"].lower()
    assert "fw_admin_token=" in cookie
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/" in cookie
    assert client.get("/api/private").status_code == 200


@pytest.mark.parametrize("token", ["wrong-token", ""])
def test_auth_session_rejects_invalid_token(client, token):
    response = client.get("/api/auth/session", params={"token": token}, follow_redirects=False)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_auth_session_rejects_query_token_when_auth_disabled(client, monkeypatch):
    monkeypatch.delenv("FLOATWINDOW_ADMIN_TOKEN", raising=False)
    response = client.get("/api/auth/session", params={"token": TOKEN}, follow_redirects=False)
    assert response.status_code == 401


def test_cors_rejects_arbitrary_origin(client):
    response = client.options("/api/private", headers={
        "Origin": "https://evil.example",
        "X-FloatWindow-Token": TOKEN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "X-FloatWindow-Token",
    })
    assert response.status_code in (400, 401)
    assert "access-control-allow-origin" not in response.headers
    response = client.get("/api/private", headers={
        "Origin": "https://evil.example",
        "X-FloatWindow-Token": TOKEN,
    })
    assert "access-control-allow-origin" not in response.headers


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_cors_allows_local_dev_token_header(client, origin):
    response = client.options("/api/private", headers={
        "Origin": origin,
        "X-FloatWindow-Token": TOKEN,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "X-FloatWindow-Token",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "x-floatwindow-token" in response.headers["access-control-allow-headers"].lower()


def test_main_app_cors_does_not_allow_wildcard(monkeypatch):
    # 載入實際管理 app，只替換會啟動模型或寫入設定／日誌的相依模組。
    api_module = ModuleType("backend.api")
    api_module.routes = SimpleNamespace(register_routes=lambda app: None)
    config_module = ModuleType("backend.config")
    config_module.settings = SimpleNamespace(
        APP_NAME="test", APP_VERSION="test", API_PREFIX="/api",
    )
    logging_module = ModuleType("backend.core.logging_setup")
    logging_module.configure_logging = lambda *args, **kwargs: "test.log"
    monkeypatch.setitem(sys.modules, "backend.api", api_module)
    monkeypatch.setitem(sys.modules, "backend.config", config_module)
    monkeypatch.setitem(sys.modules, "backend.core.logging_setup", logging_module)
    source = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("_admin_auth_main_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cors = next(item for item in module.app.user_middleware if item.cls is CORSMiddleware)
    assert "*" not in cors.kwargs.get("allow_origins", [])
    assert cors.kwargs.get("allow_origin_regex") == DEV_ORIGIN_REGEX
