import yaml
import pytest

from backend.core.config_manager import ConfigManager


def test_window_state_save_preserves_settings_written_by_another_manager(tmp_path):
    config_path = tmp_path / "config.yaml"
    settings_manager = ConfigManager(config_path)
    window_manager = ConfigManager(config_path)

    translation = settings_manager.get_config()["translation"].copy()
    translation["target_language"] = "Japanese"
    settings_manager.update_section("translation", translation)

    window_manager.save_window_state("main_window", {
        "x": 10,
        "y": 20,
        "width": 900,
        "height": 700,
    })

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["translation"]["target_language"] == "Japanese"
    assert saved["ui"]["windows"]["main_window"]["width"] == 900


def test_save_error_is_propagated_and_does_not_corrupt_existing_file(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    manager = ConfigManager(config_path)
    original = config_path.read_text(encoding="utf-8")

    def fail_replace(*_args):
        raise PermissionError("read only")

    monkeypatch.setattr("backend.core.config_manager.os.replace", fail_replace)

    with pytest.raises(PermissionError, match="read only"):
        manager.update_section("general", {"log_level": "DEBUG"})

    assert config_path.read_text(encoding="utf-8") == original
    assert not list(tmp_path.glob("*.tmp"))
