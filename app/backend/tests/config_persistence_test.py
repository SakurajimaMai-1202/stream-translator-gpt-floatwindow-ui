import re
from pathlib import Path

import yaml

from backend.core.config_manager import ConfigManager


APP_DIR = Path(__file__).resolve().parents[2]
SETTINGS_VIEW = APP_DIR / "frontend" / "src" / "views" / "SettingsView.vue"
EXAMPLE_CONFIG = APP_DIR / "config.example.yaml"
TRANSLATOR_SOURCE = APP_DIR / "backend" / "core" / "translator.py"
RUNTIME_MAIN_SOURCE = APP_DIR.parent / "stream-translator-gpt" / "stream_translator_gpt" / "main.py"
LIVE_AUDIO_KEYS = {
    "min_audio_length",
    "max_audio_length",
    "target_audio_length",
    "continuous_no_speech_threshold",
    "disable_dynamic_no_speech_threshold",
    "prefix_retention_length",
    "vad_enabled",
    "vad_threshold",
    "disable_dynamic_vad_threshold",
    "vad_every_n_frames",
    "vad_backend",
    "firered_vad_model_path",
}
REMOVED_AUDIO_KEYS = {
    "chunk_gap_threshold",
    "vad_neg_threshold",
    "vad_min_speech_duration_ms",
    "vad_min_silence_duration_ms",
    "vad_window_size_samples",
    "vad_speech_pad_ms",
    "realtime_processing",
}


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


def test_live_audio_defaults_match_example_yaml_and_ui():
    source = SETTINGS_VIEW.read_text(encoding="utf-8")
    example = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    defaults = ConfigManager.DEFAULT_CONFIG

    assert example["input"]["device_recording_interval"] == 0.1
    assert defaults["input"]["device_recording_interval"] == 0.1
    assert example["audio_slicing_vad"] == defaults["audio_slicing_vad"]
    assert set(example["audio_slicing_vad"]) == LIVE_AUDIO_KEYS

    for key in LIVE_AUDIO_KEYS:
        assert f"localConfig.audio_slicing_vad.{key}" in source
    for key in REMOVED_AUDIO_KEYS:
        assert f"localConfig.audio_slicing_vad.{key}" not in source


def test_vad_controls_are_supported_by_runtime_cli_contract():
    translator_source = TRANSLATOR_SOURCE.read_text(encoding="utf-8")
    runtime_source = RUNTIME_MAIN_SOURCE.read_text(encoding="utf-8")

    for flag in ("disable_vad", "vad_every_n_frames"):
        assert f"'{flag}'" in translator_source
        assert f"'--{flag}'" in runtime_source

    assert "disable_vad=disable_vad" in runtime_source
    assert "vad_every_n_frames=vad_every_n_frames" in runtime_source
    for key, value in {
        "device_recording_interval": "0.1",
        "min_audio_length": "0.7",
        "target_audio_length": "3.0",
        "max_audio_length": "6.0",
        "continuous_no_speech_threshold": "0.5",
        "prefix_retention_length": "0.25",
    }.items():
        assert f"kwargs.get('{key}', {value})" in runtime_source


def test_translation_pipeline_controls_are_supported_by_runtime_cli_contract():
    translator_source = TRANSLATOR_SOURCE.read_text(encoding="utf-8")
    runtime_source = RUNTIME_MAIN_SOURCE.read_text(encoding="utf-8")
    flags = {
        "translation_provider",
        "translation_model_family",
        "translation_output_format",
        "translation_max_concurrency",
        "translation_max_output_tokens",
        "disable_paired_subtitle_mode",
        "disable_asr_overlap_deduplication",
        "disable_subtitle_assembler",
        "subtitle_assembler_wait_ms",
        "subtitle_assembler_max_duration",
        "subtitle_assembler_gap_threshold",
    }

    for flag in flags:
        assert f"'{flag}'" in translator_source
        assert f"'--{flag}'" in runtime_source


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


def test_repeated_config_reads_use_memory_cache(tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_section("general", {"log_level": "DEBUG"})
    first = manager.get_config()

    def fail_disk_read():
        raise AssertionError("unchanged config should not be parsed again")

    monkeypatch.setattr(manager, "_read_current_config", fail_disk_read)
    second = manager.get_config()

    assert second == first


def test_config_cache_refreshes_after_external_write(tmp_path):
    config_path = tmp_path / "config.yaml"
    reader = ConfigManager(config_path)
    writer = ConfigManager(config_path)

    assert reader.get_config()["general"]["log_level"] == "INFO"
    writer.update_section("general", {"log_level": "WARNING"})

    assert reader.get_config()["general"]["log_level"] == "WARNING"


def test_get_config_returns_isolated_snapshot(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    snapshot = manager.get_config()
    snapshot["general"]["log_level"] = "MUTATED"

    assert manager.get_config()["general"]["log_level"] == "INFO"


def test_subtitle_latency_style_has_independent_color():
    defaults = ConfigManager.DEFAULT_CONFIG["subtitle_settings"]

    assert defaults["showLatency"] is False
    assert defaults["latencyColor"] == "#7DD3FC"
