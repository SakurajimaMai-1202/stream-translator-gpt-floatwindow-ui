import re
from pathlib import Path

import yaml

from backend.core.config_manager import ConfigManager


APP_DIR = Path(__file__).resolve().parents[2]
SETTINGS_VIEW = APP_DIR / "frontend" / "src" / "views" / "SettingsView.vue"
EXAMPLE_CONFIG = APP_DIR / "config.example.yaml"


def test_config_changes_survive_new_manager(tmp_path):
    config_path = tmp_path / "config.yaml"
    manager = ConfigManager(config_path)

    manager.update_config({
        "general": {"log_level": "DEBUG"},
        "translation": {"translation_timeout": 37},
        "output": {"output_txt": True},
    })

    reloaded = ConfigManager(config_path).get_config()
    assert reloaded["general"]["log_level"] == "DEBUG"
    assert reloaded["translation"]["translation_timeout"] == 37
    assert reloaded["output"]["output_txt"] is True


def test_stale_window_manager_does_not_overwrite_saved_settings(tmp_path):
    config_path = tmp_path / "config.yaml"
    window_manager = ConfigManager(config_path)
    backend_manager = ConfigManager(config_path)

    backend_manager.update_section("translation", {
        "backend": "gemini",
        "target_language": "Japanese",
    })
    window_manager.save_window_state("main_window", {
        "x": 321,
        "y": 123,
        "width": 900,
        "height": 700,
    })

    reloaded = ConfigManager(config_path).get_config()
    assert reloaded["translation"]["backend"] == "gemini"
    assert reloaded["translation"]["target_language"] == "Japanese"
    assert reloaded["ui"]["windows"]["main_window"]["x"] == 321


def test_all_settings_view_bindings_exist_in_yaml_and_defaults():
    source = SETTINGS_VIEW.read_text(encoding="utf-8")
    paths = sorted(set(re.findall(
        r'v-model(?:\.\w+)*="localConfig\.([^\"]+)"',
        source,
    )))
    example = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))

    assert len(paths) >= 60
    for dotted_path in paths:
        for config in (example, ConfigManager.DEFAULT_CONFIG):
            value = config
            for key in dotted_path.split("."):
                assert isinstance(value, dict) and key in value, dotted_path
                value = value[key]


def test_write_failure_is_not_reported_as_success(tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.yaml")

    def fail_replace(_source, _destination):
        raise PermissionError("read-only destination")

    monkeypatch.setattr("backend.core.config_manager.os.replace", fail_replace)

    try:
        manager.update_section("general", {"log_level": "ERROR"})
    except PermissionError as error:
        assert "read-only destination" in str(error)
    else:
        raise AssertionError("write failure must propagate to the API")
