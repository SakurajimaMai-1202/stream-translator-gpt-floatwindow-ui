import math

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import config as config_api
from backend.core.config_manager import ConfigManager, ConfigValidationError


@pytest.fixture
def config_client(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    manager = ConfigManager(path)
    monkeypatch.setattr(config_api, "get_config_manager", lambda: manager)

    async def publish(*args, **kwargs):
        pass

    monkeypatch.setattr(config_api, "publish_app_event", publish)
    app = FastAPI()
    app.include_router(config_api.router)
    with TestClient(app) as client:
        yield client, manager, path


def save(client, method, audio):
    if method == "put":
        return client.put("/config", json={"audio_slicing_vad": audio})
    return client.patch("/config/audio_slicing_vad", json=audio)


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("mode,maximum,label", [
    ("legacy", "max_audio_length", "最大音訊長度"),
    ("omnivad_native", "omnivad_max_audio_length", "原生模式最大音訊長度"),
])
def test_min_above_effective_max(config_client, method, mode, maximum, label):
    client, manager, path = config_client
    before = path.read_bytes()
    response = save(client, method, {
        "slicing_mode": mode, "min_audio_length": 99, maximum: 6,
    })
    assert response.status_code == 422
    assert response.json()["detail"] == f"最小音訊長度（99 秒）不可大於{label}（6 秒）"
    assert path.read_bytes() == before


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("field,label", [
    ("min_audio_length", "最小音訊長度"),
    ("target_audio_length", "目標音訊長度"),
    ("max_audio_length", "最大音訊長度"),
    ("omnivad_max_audio_length", "原生模式最大音訊長度"),
])
@pytest.mark.parametrize("value", ["", None, "0.7", 0, -1, True])
def test_invalid_number(config_client, method, field, label, value):
    client, manager, path = config_client
    before = path.read_bytes()
    mode = "omnivad_native" if field == "omnivad_max_audio_length" else "legacy"
    response = save(client, method, {"slicing_mode": mode, field: value})
    assert response.status_code == 422
    assert response.json()["detail"] == f"{label}必須是大於 0 的數字"
    assert path.read_bytes() == before


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("value", ["", None, "bad", 0, -1, True])
def test_native_ignores_hidden_target_and_max(config_client, method, value):
    client, _, _ = config_client
    assert save(client, method, {
        "slicing_mode": "omnivad_native", "min_audio_length": 1,
        "omnivad_max_audio_length": 6,
        "target_audio_length": value, "max_audio_length": value,
    }).status_code == 200


@pytest.mark.parametrize("method", ["put", "patch"])
def test_legacy_ignores_native_max(config_client, method):
    client, _, _ = config_client
    assert save(client, method, {
        "slicing_mode": "legacy", "omnivad_max_audio_length": None,
    }).status_code == 200


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_nonfinite_numbers(config_client, value):
    _, manager, path = config_client
    before = path.read_bytes()
    with pytest.raises(ConfigValidationError, match="最小音訊長度"):
        manager.update_config({"audio_slicing_vad": {"min_audio_length": value}})
    assert path.read_bytes() == before


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("target", [0.5, 9])
def test_target_range_only_in_legacy(config_client, method, target):
    client, _, path = config_client
    before = path.read_bytes()
    response = save(client, method, {"slicing_mode": "legacy", "target_audio_length": target})
    assert response.status_code == 422
    assert "目標音訊長度" in response.json()["detail"]
    assert path.read_bytes() == before
    assert save(client, method, {"slicing_mode": "omnivad_native", "target_audio_length": target}).status_code == 200


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("target", [1, 6])
def test_valid_update_inclusive_bounds(config_client, method, target):
    client, _, path = config_client
    response = save(client, method, {
        "slicing_mode": "legacy", "min_audio_length": 1,
        "max_audio_length": 6, "target_audio_length": target,
    })
    assert response.status_code == 200
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["audio_slicing_vad"]["target_audio_length"] == target


@pytest.mark.parametrize("method", ["put", "patch"])
def test_unchanged_legacy_bad_section_and_other_sections(config_client, method):
    client, manager, path = config_client
    config = manager.get_config()
    config["audio_slicing_vad"]["min_audio_length"] = 99
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    bad_audio = ConfigManager(path).get_config()["audio_slicing_vad"]
    assert bad_audio["min_audio_length"] == 99
    assert save(client, method, bad_audio).status_code == 200
    response = client.put("/config", json={
        "audio_slicing_vad": bad_audio, "general": {"log_level": "DEBUG"},
    })
    assert response.status_code == 200
    assert client.patch("/config/general", json={"log_level": "WARNING"}).status_code == 200
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["general"]["log_level"] == "WARNING"
    assert saved["audio_slicing_vad"]["min_audio_length"] == 99


@pytest.mark.parametrize("method", ["put", "patch"])
def test_structural_error_remains_400(config_client, method):
    client, _, path = config_client
    before = path.read_bytes()
    if method == "put":
        response = client.put("/config", json={"audio_slicing_vad": None})
    else:
        response = client.patch("/config/translation", json={"custom_models": {}})
    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid configuration structure"
    assert path.read_bytes() == before


@pytest.mark.parametrize("method", ["put", "patch"])
def test_boolean_is_not_unchanged_numeric_one(config_client, method):
    client, manager, path = config_client
    manager.update_config({"audio_slicing_vad": {"min_audio_length": 1}})
    before = path.read_bytes()
    response = save(client, method, {"min_audio_length": True})
    assert response.status_code == 422
    assert path.read_bytes() == before


@pytest.mark.parametrize("mode,maximum", [
    ("legacy", "max_audio_length"),
    ("omnivad_native", "omnivad_max_audio_length"),
])
def test_partial_update_validates_against_saved_max(config_client, mode, maximum):
    client, manager, path = config_client
    manager.update_config({"audio_slicing_vad": {
        "slicing_mode": mode, maximum: 5, "target_audio_length": 4,
    }})
    before = path.read_bytes()
    response = save(client, "patch", {"min_audio_length": 6})
    assert response.status_code == 422
    assert "（5 秒）" in response.json()["detail"]
    assert path.read_bytes() == before


def test_audio_preprocess_defaults_and_legacy_config_compat(tmp_path):
    path = tmp_path / "config.yaml"
    # Simulate an old config.yaml without the 4 audio_preprocess keys.
    path.write_text(
        yaml.safe_dump({"audio_slicing_vad": {"min_audio_length": 0.7}}, allow_unicode=True),
        encoding="utf-8",
    )
    manager = ConfigManager(path)
    audio = manager.get_config()["audio_slicing_vad"]
    assert audio["audio_preprocess_enabled"] is False
    assert "audio_agc_enabled" not in audio
    assert audio["audio_agc_max_gain_db"] == pytest.approx(30.0)
    assert audio["audio_highpass_enabled"] is False

    args = manager.to_main_args()
    assert args["audio_preprocess"] is False
    assert "disable_audio_agc" not in args
    assert args["audio_agc_max_gain_db"] is None
    assert args["audio_highpass"] is False


def test_audio_preprocess_hand_edited_config_tolerance(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.safe_dump({
            "audio_slicing_vad": {
                "audio_preprocess_enabled": "false",
                "audio_highpass_enabled": "false",
                "audio_agc_max_gain_db": None,
            }
        }, allow_unicode=True),
        encoding="utf-8",
    )
    args = ConfigManager(path).to_main_args()
    assert args["audio_preprocess"] is False
    assert args["audio_highpass"] is False
    assert args["audio_agc_max_gain_db"] is None

    path.write_text(
        yaml.safe_dump({
            "audio_slicing_vad": {
                "audio_preprocess_enabled": True,
                "audio_agc_max_gain_db": "abc",
                "audio_highpass_enabled": None,
            }
        }, allow_unicode=True),
        encoding="utf-8",
    )
    args = ConfigManager(path).to_main_args()
    assert args["audio_preprocess"] is True
    assert args["audio_agc_max_gain_db"] == pytest.approx(30.0)
    assert args["audio_highpass"] is False

    path.write_text(
        yaml.safe_dump({
            "audio_slicing_vad": {
                "audio_preprocess_enabled": True,
                "audio_agc_max_gain_db": 99,
            }
        }, allow_unicode=True),
        encoding="utf-8",
    )
    assert ConfigManager(path).to_main_args()["audio_agc_max_gain_db"] == pytest.approx(40.0)

    path.write_text(
        yaml.safe_dump({
            "audio_slicing_vad": {
                "audio_preprocess_enabled": True,
                "audio_agc_max_gain_db": 2,
            }
        }, allow_unicode=True),
        encoding="utf-8",
    )
    assert ConfigManager(path).to_main_args()["audio_agc_max_gain_db"] == pytest.approx(6.0)


def test_audio_preprocess_enabled_maps_to_main_args(config_client):
    _, manager, _ = config_client
    manager.update_section("audio_slicing_vad", {
        "audio_preprocess_enabled": True,
        "audio_agc_max_gain_db": 24.0,
        "audio_highpass_enabled": True,
    })
    args = manager.to_main_args()
    assert args["audio_preprocess"] is True
    assert args["audio_agc_max_gain_db"] == pytest.approx(24.0)
    assert args["audio_highpass"] is True


def test_highpass_flag_not_sent_while_preprocess_is_off(config_client):
    _, manager, _ = config_client
    manager.update_section("audio_slicing_vad", {
        "audio_preprocess_enabled": False,
        "audio_highpass_enabled": True,
    })
    args = manager.to_main_args()
    assert args["audio_preprocess"] is False
    assert args["audio_highpass"] is False
    assert args["audio_agc_max_gain_db"] is None


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("value", [5, 5.9, 40.1, 41, 0, -10, True, False, None, "20", ""])
def test_audio_agc_max_gain_db_rejects_invalid(config_client, method, value):
    client, _, path = config_client
    before = path.read_bytes()
    response = save(client, method, {"audio_agc_max_gain_db": value})
    assert response.status_code == 422
    assert "最大放大倍數" in response.json()["detail"]
    assert path.read_bytes() == before


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_audio_agc_max_gain_db_rejects_nonfinite(config_client, value):
    _, manager, path = config_client
    before = path.read_bytes()
    with pytest.raises(ConfigValidationError, match="最大放大倍數"):
        manager.update_config({"audio_slicing_vad": {"audio_agc_max_gain_db": value}})
    assert path.read_bytes() == before


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("gain", [6, 30.0, 40])
def test_audio_agc_max_gain_db_accepts_inclusive_bounds(config_client, method, gain):
    client, _, path = config_client
    response = save(client, method, {"audio_agc_max_gain_db": gain})
    assert response.status_code == 200
    assert yaml.safe_load(path.read_text(encoding="utf-8"))["audio_slicing_vad"]["audio_agc_max_gain_db"] == gain


@pytest.mark.parametrize("method", ["put", "patch"])
@pytest.mark.parametrize("field", [
    "audio_preprocess_enabled",
    "audio_highpass_enabled",
])
@pytest.mark.parametrize("value", [1, 0, "true", None])
def test_audio_preprocess_booleans_reject_non_bool(config_client, method, field, value):
    client, _, path = config_client
    before = path.read_bytes()
    response = save(client, method, {field: value})
    assert response.status_code == 422
    assert "布林值" in response.json()["detail"]
    assert path.read_bytes() == before
