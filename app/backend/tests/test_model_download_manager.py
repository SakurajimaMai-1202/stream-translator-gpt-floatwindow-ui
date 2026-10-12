import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Add project root to path
sys.path.append(os.getcwd())

from backend.core.model_download_manager import ModelDownloadManager


def test_normalize_repo_id_for_qwen3_asr():
    manager = ModelDownloadManager()
    repo_id = manager._normalize_repo_id("qwen3-asr", "Qwen/Qwen3-ASR-1.7B")
    assert repo_id == "Qwen/Qwen3-ASR-1.7B"


def test_faster_whisper_is_not_supported_by_cpu_sherpa_backend():
    manager = ModelDownloadManager()
    with pytest.raises(ValueError, match="sherpa-onnx"):
        manager._validate_model_id("faster-whisper", "large-v3-turbo", "cpu")


def test_list_downloaded_gpu_models_are_tagged_as_gpu(monkeypatch):
    manager = ModelDownloadManager()

    fake_cache = SimpleNamespace(
        repos=[
            SimpleNamespace(
                repo_id="Qwen/Qwen3-ASR-1.7B",
                size_on_disk=456,
                repo_path=Path("/tmp/fake-qwen"),
            ),
            SimpleNamespace(
                repo_id="mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                size_on_disk=123,
                repo_path=Path("/tmp/fake-turbo"),
            ),
        ]
    )

    import types
    fake_hub = types.ModuleType("huggingface_hub")
    fake_hub.scan_cache_dir = lambda *args, **kwargs: fake_cache
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)

    models = manager.list_downloaded_models()

    by_id = {item.model_id: item for item in models}
    assert by_id["Qwen/Qwen3-ASR-1.7B"].compute_backend == "gpu"
    assert by_id["large-v3-turbo"].compute_backend == "gpu"


def test_fun_asr_nano_model_ids_are_supported():
    manager = ModelDownloadManager()
    model_ids = (
        "FunAudioLLM/Fun-ASR-Nano-2512",
        "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
    )

    for model_id in model_ids:
        assert manager._validate_model_id("fun-asr-nano", model_id) == model_id
        assert manager._normalize_repo_id("fun-asr-nano", model_id) == model_id
