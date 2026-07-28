import subprocess
import copy
from pathlib import Path

from backend.config import settings
from backend.core import cookie_manager
from backend.core.config_manager import ConfigManager


def test_detect_cookie_platform_uses_hostname_not_filename():
    assert cookie_manager.detect_cookie_platform("https://www.youtube.com/watch?v=test") == "youtube"
    assert cookie_manager.detect_cookie_platform("https://www.tiktok.com/@creator/live") == "tiktok"
    assert cookie_manager.detect_cookie_platform("https://x.com/i/spaces/test") == "twitter"
    assert cookie_manager.detect_cookie_platform("https://example.com/youtube") is None


def test_resolve_cookie_path_prefers_site_and_keeps_legacy_fallback():
    config = {
        "cookies": "legacy.txt",
        "cookies_by_site": {
            "youtube": "youtube.txt",
            "tiktok": "tiktok.txt",
        },
    }

    assert cookie_manager.resolve_cookie_path("https://youtu.be/test", config) == "youtube.txt"
    assert cookie_manager.resolve_cookie_path("https://www.tiktok.com/live", config) == "tiktok.txt"
    assert cookie_manager.resolve_cookie_path("https://example.com/live", config) == "legacy.txt"


def test_config_manager_passes_url_specific_cookie_to_runtime(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = copy.deepcopy(ConfigManager.DEFAULT_CONFIG)
    config["input"].update({
        "url": "https://www.tiktok.com/@creator/live",
        "cookies": "legacy.txt",
        "cookies_by_site": {
            "youtube": "youtube.txt",
            "tiktok": "tiktok.txt",
        },
    })

    args = manager.to_main_args(config)

    assert args["cookies"] == "tiktok.txt"


def test_filter_cookie_file_keeps_only_selected_platform_and_httponly(tmp_path):
    source = tmp_path / "all.txt"
    destination = tmp_path / "tiktok.txt"
    source.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tyoutube-secret\n"
        "#HttpOnly_.tiktok.com\tTRUE\t/\tTRUE\t0\tsessionid\ttiktok-secret\n"
        ".tiktokcdn.com\tTRUE\t/\tTRUE\t0\tcdn_token\tcdn-secret\n",
        encoding="utf-8",
    )

    count = cookie_manager._filter_netscape_cookie_file(
        source,
        destination,
        cookie_manager.COOKIE_PLATFORMS["tiktok"],
    )

    content = destination.read_text(encoding="utf-8")
    assert count == 2
    assert "tiktok-secret" in content
    assert "cdn-secret" in content
    assert "youtube-secret" not in content
    assert content.startswith("# Netscape HTTP Cookie File\n")


def test_export_platform_cookies_uses_managed_path_and_filters(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    runtime_python = tmp_path / "python.exe"
    runtime_python.write_bytes(b"")
    monkeypatch.setattr(settings, "CONFIG_FILE", config_path)
    monkeypatch.setattr(cookie_manager, "_resolve_runtime_python", lambda: runtime_python)

    def fake_run(command, **_kwargs):
        exported = Path(command[-1])
        exported.write_text(
            "# Netscape HTTP Cookie File\n"
            ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tyoutube-secret\n"
            ".tiktok.com\tTRUE\t/\tTRUE\t0\tsessionid\ttiktok-secret\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(cookie_manager.subprocess, "run", fake_run)

    result = cookie_manager.export_platform_cookies("tiktok", "edge", "Profile 1")

    destination = tmp_path / "cookies" / "tiktok.cookies.txt"
    assert result["path"] == str(destination)
    assert result["cookie_count"] == 1
    assert result["browser"] == "edge"
    assert result["profile"] == "Profile 1"
    assert "tiktok-secret" in destination.read_text(encoding="utf-8")


def test_export_rejects_unknown_platform_and_browser():
    try:
        cookie_manager.export_platform_cookies("unknown", "chrome")
    except ValueError as exc:
        assert "不支援的 Cookies 平台" in str(exc)
    else:
        raise AssertionError("unknown platform should fail")

    try:
        cookie_manager.export_platform_cookies("youtube", "unknown")
    except ValueError as exc:
        assert "不支援的瀏覽器" in str(exc)
    else:
        raise AssertionError("unknown browser should fail")


def test_chromium_cookie_database_lock_has_actionable_error():
    output = (
        "yt_dlp.utils.DownloadError: Could not copy Chrome cookie database. "
        "See https://github.com/yt-dlp/yt-dlp/issues/7271 for more info"
    )

    try:
        cookie_manager._raise_browser_export_error("chrome", output)
    except cookie_manager.BrowserCookieDatabaseLockedError as exc:
        message = str(exc)
        assert "完全關閉" in message
        assert "chrome.exe" in message
        assert "Firefox" in message
        assert "Traceback" not in message
    else:
        raise AssertionError("locked Chromium cookie database should have a dedicated error")


def test_chromium_dpapi_failure_explains_app_bound_encryption():
    try:
        cookie_manager._raise_browser_export_error(
            "edge",
            "ERROR: Failed to decrypt with DPAPI",
        )
    except cookie_manager.BrowserCookieDecryptionUnsupportedError as exc:
        message = str(exc)
        assert "App-Bound Encryption" in message
        assert "不是版本過舊" in message
        assert "Firefox" in message
        assert "cookies.txt" in message
    else:
        raise AssertionError("DPAPI failure should have a dedicated error")


def test_import_platform_cookie_file_uses_managed_destination(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "CONFIG_FILE", tmp_path / "config.yaml")
    source = tmp_path / "exported.txt"
    source.write_text(
        "# Netscape HTTP Cookie File\n"
        ".youtube.com\tTRUE\t/\tTRUE\t0\tSID\tyoutube-secret\n"
        ".tiktok.com\tTRUE\t/\tTRUE\t0\tsessionid\ttiktok-secret\n",
        encoding="utf-8",
    )

    result = cookie_manager.import_platform_cookie_file("youtube", source)

    destination = tmp_path / "cookies" / "youtube.cookies.txt"
    assert result["source"] == "file"
    assert result["path"] == str(destination)
    assert result["cookie_count"] == 1
    assert "youtube-secret" in destination.read_text(encoding="utf-8")
    assert "tiktok-secret" not in destination.read_text(encoding="utf-8")
