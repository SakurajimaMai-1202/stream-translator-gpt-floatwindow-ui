import logging

import pytest

from backend.config import settings
from backend.core.admin_host import get_admin_host


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    path = tmp_path / "config.yaml"
    monkeypatch.setattr(settings, "CONFIG_FILE", path)
    monkeypatch.delenv("FLOATWINDOW_ADMIN_HOST", raising=False)
    return path


def test_admin_host_defaults_to_loopback(isolated_config):
    isolated_config.write_text("server:\n  public_port: 8765\n", encoding="utf-8")
    assert get_admin_host() == "127.0.0.1"


def test_admin_host_missing_config_stays_loopback():
    assert get_admin_host() == "127.0.0.1"


def test_admin_host_lan_setting_listens_on_all_interfaces(isolated_config, caplog):
    isolated_config.write_text("server:\n  allow_lan_admin: true\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="backend.core.admin_host"):
        assert get_admin_host() == "0.0.0.0"
    assert "管理 API 監聽非本機位址" in caplog.text


@pytest.mark.parametrize("value", ["'true'", "1", "yes"])
def test_admin_host_lan_setting_requires_real_true(isolated_config, value):
    # Only an explicit boolean opens the port; a stray string must not.
    isolated_config.write_text(f"server:\n  allow_lan_admin: {value}\n", encoding="utf-8")
    expected = "0.0.0.0" if value == "yes" else "127.0.0.1"
    assert get_admin_host() == expected


def test_admin_host_env_override_beats_lan_setting(monkeypatch, isolated_config):
    isolated_config.write_text("server:\n  allow_lan_admin: true\n", encoding="utf-8")
    monkeypatch.setenv("FLOATWINDOW_ADMIN_HOST", "127.0.0.1")
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
