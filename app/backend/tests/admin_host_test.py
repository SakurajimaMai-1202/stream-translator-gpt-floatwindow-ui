import logging

from backend.core.admin_host import get_admin_host


def test_admin_host_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("FLOATWINDOW_ADMIN_HOST", raising=False)
    assert get_admin_host() == "127.0.0.1"


def test_admin_host_honours_override_and_warns(monkeypatch, caplog):
    monkeypatch.setenv("FLOATWINDOW_ADMIN_HOST", "0.0.0.0")
    with caplog.at_level(logging.WARNING, logger="backend.core.admin_host"):
        assert get_admin_host() == "0.0.0.0"
    assert "管理 API 監聽非本機位址" in caplog.text


def test_admin_host_loopback_override_does_not_warn(monkeypatch, caplog):
    monkeypatch.setenv("FLOATWINDOW_ADMIN_HOST", "::1")
    with caplog.at_level(logging.WARNING, logger="backend.core.admin_host"):
        assert get_admin_host() == "::1"
    assert not caplog.records
