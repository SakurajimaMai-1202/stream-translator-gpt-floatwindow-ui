import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core import admin_auth
from backend.core.admin_auth import LAN_SESSION_COOKIE, LoginLimiter, register_admin_auth

TOKEN = "desktop-token"
REMOTE = ("192.168.100.61", 40000)
LOCAL = ("127.0.0.1", 40000)


@pytest.fixture
def make_client(monkeypatch):
    monkeypatch.setenv("FLOATWINDOW_ADMIN_TOKEN", TOKEN)
    monkeypatch.setattr(admin_auth, "login_limiter", LoginLimiter())
    password = {"value": "correct horse"}

    def build(client=REMOTE):
        app = FastAPI()
        register_admin_auth(app, "/api", lan_password=lambda: password["value"])

        @app.get("/api/private")
        async def private():
            return {"ok": True}

        @app.get("/api/health")
        async def health():
            return {"status": "ok"}

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            return {"spa": full_path}

        return TestClient(app, client=client, follow_redirects=False)

    build.password = password
    return build


def login(client, password):
    return client.post("/api/auth/login", json={"password": password})


def test_local_desktop_never_needs_password(make_client):
    client = make_client(LOCAL)
    assert client.get("/").json() == {"spa": ""}
    assert client.get("/api/private", headers={"X-FloatWindow-Token": TOKEN}).status_code == 200
    assert client.get("/api/private").status_code == 401


def test_remote_is_sent_to_login_page(make_client):
    client = make_client()
    response = client.get("/settings")
    assert response.status_code == 302 and response.headers["location"] == "/login"
    assert client.get("/api/private").status_code == 401
    assert client.get("/api/health").status_code == 200
    page = client.get("/login")
    assert page.status_code == 200 and "密碼" in page.text


def test_remote_login_unlocks_ui_and_api(make_client):
    client = make_client()
    response = login(client, "correct horse")
    assert response.status_code == 200
    cookie = response.cookies.get(LAN_SESSION_COOKIE)
    assert cookie and "correct horse" not in cookie
    assert client.get("/settings").json() == {"spa": "settings"}
    assert client.get("/api/private").status_code == 200


def test_wrong_password_rejected_and_rate_limited(make_client):
    client = make_client()
    for _ in range(5):
        assert login(client, "wrong").status_code == 401
    # Even the right password is refused while blocked.
    assert login(client, "correct horse").status_code == 429


def test_changing_password_invalidates_sessions(make_client):
    client = make_client()
    assert login(client, "correct horse").status_code == 200
    make_client.password["value"] = "new password"
    assert client.get("/api/private").status_code == 401


def test_no_password_means_no_remote_login(make_client):
    make_client.password["value"] = ""
    client = make_client()
    assert login(client, "").status_code == 403
    assert client.get("/").status_code == 302


def test_forwarded_request_counts_as_remote(make_client):
    # A proxy on this PC connects from 127.0.0.1 but still forwards an outside client.
    client = make_client(LOCAL)
    response = client.get("/", headers={"X-Forwarded-For": "203.0.113.5"})
    assert response.status_code == 302


def test_remote_desktop_token_still_accepted(make_client):
    client = make_client()
    assert client.get("/api/private", headers={"X-FloatWindow-Token": TOKEN}).status_code == 200


def test_limiter_window_expires():
    now = [0.0]
    limiter = LoginLimiter(max_failures=2, window=10, clock=lambda: now[0])
    limiter.record_failure(); limiter.record_failure()
    assert limiter.blocked()
    now[0] = 10.0
    assert not limiter.blocked()
