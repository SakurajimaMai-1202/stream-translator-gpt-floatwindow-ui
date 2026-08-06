from pathlib import Path

import yaml

from backend.config import settings
from backend.core.model_download_manager import ModelDownloadManager
from backend.core import model_download_manager as model_manager_module
from backend.core.portable_paths import (
    apply_model_cache_environment,
    get_huggingface_hub_cache,
    get_model_storage_root,
)


def test_default_model_storage_is_next_to_app(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"models": {"storage_path": ""}}), encoding="utf-8")
    monkeypatch.setattr(settings, "CONFIG_FILE", config_path)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)

    assert get_model_storage_root() == (tmp_path / "models" / "huggingface").resolve()
    assert get_huggingface_hub_cache() == (tmp_path / "models" / "huggingface" / "hub").resolve()


def test_custom_relative_model_storage_resolves_from_app_root(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump({"models": {"storage_path": "model-data"}}), encoding="utf-8")
    monkeypatch.setattr(settings, "CONFIG_FILE", config_path)
    monkeypatch.setattr(settings, "BASE_DIR", tmp_path)

    env = apply_model_cache_environment({"PATH": "example"})

    assert env["HF_HOME"] == str((tmp_path / "model-data").resolve())
    assert env["HUGGINGFACE_HUB_CACHE"] == str((tmp_path / "model-data" / "hub").resolve())
    assert env["MODELSCOPE_CACHE"] == str((tmp_path / "model-data" / "modelscope").resolve())
    assert env["PATH"] == "example"


def test_delete_model_only_removes_expected_repo(monkeypatch, tmp_path):
    manager = ModelDownloadManager()
    cache_root = tmp_path / "hub"
    repo_dir = cache_root / "models--Qwen--Qwen3-ASR-1.7B"
    repo_dir.mkdir(parents=True)
    (repo_dir / "model.bin").write_bytes(b"test")
    unrelated = cache_root / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")
    monkeypatch.setattr(manager, "_get_hf_cache_dir", lambda: cache_root)

    deleted = manager.delete_model("qwen3-asr", "Qwen/Qwen3-ASR-1.7B")

    assert deleted == repo_dir.resolve()
    assert not repo_dir.exists()
    assert unrelated.exists()


def test_sensevoice_model_download_metadata_and_delete(monkeypatch, tmp_path):
    manager = ModelDownloadManager()
    cache_root = tmp_path / "modelscope"
    repo_dir = cache_root / "models" / "iic" / "SenseVoiceSmall"
    repo_dir.mkdir(parents=True)
    (repo_dir / "model.bin").write_bytes(b"test")
    monkeypatch.setattr(manager, "_get_modelscope_cache_dir", lambda: cache_root)
    monkeypatch.setattr(manager, "_get_hf_cache_dir", lambda: tmp_path / "empty-hf")

    models = manager.list_downloaded_models()

    assert len(models) == 1
    assert models[0].engine == "sensevoice"
    assert models[0].model_id == "iic/SenseVoiceSmall"

    deleted = manager.delete_model("sensevoice", "iic/SenseVoiceSmall")

    assert deleted == repo_dir.resolve()
    assert not repo_dir.exists()


def test_sensevoice_legacy_modelscope_path_is_listed_and_deleted(monkeypatch, tmp_path):
    manager = ModelDownloadManager()
    cache_root = tmp_path / "modelscope"
    repo_dir = cache_root / "iic" / "SenseVoiceSmall"
    repo_dir.mkdir(parents=True)
    (repo_dir / "model.bin").write_bytes(b"test")
    monkeypatch.setattr(manager, "_get_modelscope_cache_dir", lambda: cache_root)
    monkeypatch.setattr(manager, "_get_hf_cache_dir", lambda: tmp_path / "empty-hf")

    models = manager.list_downloaded_models()

    assert len(models) == 1
    assert models[0].cache_path == str(repo_dir.resolve())

    deleted = manager.delete_model("sensevoice", "iic/SenseVoiceSmall")

    assert deleted == repo_dir.resolve()
    assert not repo_dir.exists()


def test_sherpa_model_is_listed_and_deleted_independently_from_gpu_cache(monkeypatch, tmp_path):
    manager = ModelDownloadManager()
    storage_root = tmp_path / "models"
    bundle = "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17"
    cpu_dir = storage_root / "sherpa-onnx" / bundle
    cpu_dir.mkdir(parents=True)
    (cpu_dir / "model.int8.onnx").write_bytes(b"cpu")
    (cpu_dir / "tokens.txt").write_text("tokens", encoding="utf-8")
    gpu_dir = storage_root / "modelscope" / "models" / "iic" / "SenseVoiceSmall"
    gpu_dir.mkdir(parents=True)
    (gpu_dir / "model.bin").write_bytes(b"gpu")

    monkeypatch.setattr(model_manager_module, "get_model_storage_root", lambda: storage_root)
    monkeypatch.setattr(manager, "_get_modelscope_cache_dir", lambda: storage_root / "modelscope")
    monkeypatch.setattr(manager, "_get_hf_cache_dir", lambda: storage_root / "empty-hf")

    models = manager.list_downloaded_models()
    matches = [item for item in models if item.model_id == "iic/SenseVoiceSmall"]
    assert {item.compute_backend for item in matches} == {"cpu", "gpu"}

    deleted = manager.delete_model("sensevoice", "iic/SenseVoiceSmall", "cpu")
    assert deleted == cpu_dir.resolve()
    assert not cpu_dir.exists()
    assert gpu_dir.exists()
