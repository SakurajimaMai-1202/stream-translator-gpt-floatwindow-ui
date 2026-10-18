from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import routes
from backend.core import admin_host


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("FLOATWINDOW_ADMIN_TOKEN", "tok/en+1")
    config = {"server": {"public_port": 8765, "enable_subtitle_sharing": True, "allow_lan_admin": True}}
    monkeypatch.setattr(routes, "get_config_manager", lambda: SimpleNamespace(get_config=lambda: config))
    monkeypatch.setattr(routes.socket, "getaddrinfo",
                        lambda *a, **k: [(None, None, None, None, ("192.168.1.20", 0)),
                                         (None, None, None, None, ("127.0.0.1", 0))])
    app = FastAPI()
    routes.register_routes(app)
    return TestClient(app, base_url="http://127.0.0.1:8010")


def test_lan_admin_urls_only_when_bound_to_lan(monkeypatch, client):
    monkeypatch.setattr(admin_host, "bound_host", "127.0.0.1")
    data = client.get("/api/server/info").json()
    # Enabled in config but this run still listens on loopback: needs a restart.
    assert data["allow_lan_admin"] is True
    assert data["lan_admin_active"] is False
    assert data["lan_admin_urls"] == []

    monkeypatch.setattr(admin_host, "bound_host", "0.0.0.0")
    data = client.get("/api/server/info").json()
    assert data["lan_admin_active"] is True
    assert data["lan_admin_urls"] == ["http://192.168.1.20:8010/"]
