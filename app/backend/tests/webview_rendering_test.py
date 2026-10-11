from argparse import Namespace

import pytest

from webview_rendering import apply_render_mode, read_configured_render_mode, resolve_render_mode


def _args(**overrides):
    values = {
        "disable_gpu": False,
        "enable_webview_gpu": False,
        "enable_webview_direct_composition": False,
        "disable_webview_direct_composition": False,
    }
    values.update(overrides)
    return Namespace(**values)


@pytest.fixture(autouse=True)
def _clean_flags(monkeypatch):
    monkeypatch.delenv("QTWEBENGINE_CHROMIUM_FLAGS", raising=False)
    monkeypatch.delenv("QT_OPENGL", raising=False)


def test_windows_defaults_to_gpu_compositing_with_cpu_raster():
    assert resolve_render_mode(_args(), "", platform="win32") == "software"
    assert resolve_render_mode(_args(), "", platform="linux") == "gpu"


def test_command_line_overrides_config():
    assert resolve_render_mode(_args(disable_gpu=True), "gpu", platform="win32") == "software"
    assert resolve_render_mode(_args(enable_webview_gpu=True), "software", platform="win32") == "gpu"
    assert resolve_render_mode(_args(enable_webview_direct_composition=True), "", platform="win32") == "gpu"
    assert resolve_render_mode(_args(), "software", platform="win32") == "software"


def test_gpu_safe_keeps_gpu_compositing_and_moves_raster_to_cpu(monkeypatch):
    import os

    assert apply_render_mode("gpu-safe", _args(), platform="win32") is False
    flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
    assert "--disable-gpu-rasterization" in flags
    assert "--disable-zero-copy" in flags
    assert "--disable-direct-composition" in flags
    assert "--disable-features=CalculateNativeWinOcclusion" in flags
    assert "--disable-gpu" not in flags
    assert "--disable-gpu-compositing" not in flags
    assert "QT_OPENGL" not in os.environ


def test_full_gpu_mode_does_not_restrict_raster(monkeypatch):
    import os

    assert apply_render_mode("gpu", _args(enable_webview_gpu=True), platform="win32") is False
    flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
    assert "--disable-gpu-rasterization" not in flags
    assert "--disable-direct-composition" in flags


def test_direct_composition_can_be_enabled_explicitly():
    import os

    apply_render_mode("gpu", _args(enable_webview_direct_composition=True), platform="win32")
    assert "--disable-direct-composition" not in os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()


def test_software_mode_keeps_previous_fallback_flags():
    import os

    assert apply_render_mode("software", _args(disable_gpu=True), platform="win32") is True
    flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
    assert flags == ["--disable-gpu", "--disable-gpu-compositing"]
    assert os.environ["QT_OPENGL"] == "software"


def test_external_flags_are_preserved(monkeypatch):
    import os

    monkeypatch.setenv("QTWEBENGINE_CHROMIUM_FLAGS", "--lang=zh-TW --disable-zero-copy")
    apply_render_mode("gpu-safe", _args(), platform="win32")
    flags = os.environ["QTWEBENGINE_CHROMIUM_FLAGS"].split()
    assert flags[:2] == ["--lang=zh-TW", "--disable-zero-copy"]
    assert flags.count("--disable-zero-copy") == 1


def test_config_value_is_read_and_validated(tmp_path):
    config = tmp_path / "config.yaml"
    assert read_configured_render_mode(config) == ""

    config.write_text("ui:\n  webview_rendering: Software\n", encoding="utf-8")
    assert read_configured_render_mode(config) == "software"

    config.write_text("ui:\n  webview_rendering: turbo\n", encoding="utf-8")
    assert read_configured_render_mode(config) == ""

    config.write_text("ui: null\n", encoding="utf-8")
    assert read_configured_render_mode(config) == ""

    config.write_text("ui: [\n", encoding="utf-8")
    assert read_configured_render_mode(config) == ""
