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


@pytest.fixture
def isolated_model_cache(monkeypatch, tmp_path):
    import backend.core.model_download_manager as module

    monkeypatch.setattr(module, "get_model_storage_root", lambda: tmp_path)
    monkeypatch.setattr(module, "get_modelscope_cache", lambda: tmp_path / "modelscope")
    monkeypatch.setattr(module, "get_huggingface_hub_cache", lambda: tmp_path / "hub")
    # Exercise filesystem listing as well, including tombstone filtering.
    def unavailable(*args, **kwargs):
        raise OSError("No SDK cache scan")
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(scan_cache_dir=unavailable))
    return tmp_path


def _sensevoice_files(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "model.bin").write_bytes(b"legacy fixture asset")


@pytest.mark.parametrize("layout", ["models/iic/SenseVoiceSmall", "iic/SenseVoiceSmall"])
def test_sensevoice_listing_preserves_unmarked_legacy_layouts(isolated_model_cache, layout):
    manager = ModelDownloadManager()
    path = isolated_model_cache / "modelscope" / layout
    _sensevoice_files(path)
    models = manager.list_downloaded_models()
    assert len(models) == 1
    assert models[0].model_id == "iic/SenseVoiceSmall"
    assert Path(models[0].cache_path) == path.resolve()


@pytest.mark.parametrize("backend,engine,model_id", [
    ("gpu", "faster-whisper", "tiny"),
    ("gpu", "sensevoice", "iic/SenseVoiceSmall"),
    ("cpu", "sensevoice", "iic/SenseVoiceSmall"),
])
@pytest.mark.parametrize("failure", ["rename", "cleanup", None])
def test_delete_detaches_model_before_cleanup(monkeypatch, isolated_model_cache, backend, engine, model_id, failure):
    import backend.core.model_download_manager as module

    manager = ModelDownloadManager()
    if backend == "cpu":
        bundle, required = module.SHERPA_CPU_BUNDLES[model_id]
        path = isolated_model_cache / "sherpa-onnx" / bundle
        path.mkdir(parents=True)
        for name in required:
            (path / name).write_bytes(b"asset")
    elif engine == "sensevoice":
        path = isolated_model_cache / "modelscope" / "models/iic/SenseVoiceSmall"
        _sensevoice_files(path)
    else:
        path = isolated_model_cache / "hub" / "models--Systran--faster-whisper-tiny"
        path.mkdir(parents=True)
        (path / "asset").write_bytes(b"asset")
    assert len(manager.list_downloaded_models()) == 1
    original_files = sorted(p.name for p in path.iterdir())
    if failure == "rename":
        def fail_rename(*args):
            raise PermissionError("rename blocked")
        monkeypatch.setattr(Path, "rename", fail_rename)
    else:
        real_remove = module.shutil.rmtree
        def remove(tombstone):
            assert not path.exists()
            assert manager.list_downloaded_models() == []
            assert tombstone.name.startswith(".deleted-")
            if failure == "cleanup":
                next(tombstone.iterdir()).unlink()
                raise PermissionError("cleanup blocked")
            real_remove(tombstone)
        monkeypatch.setattr(module.shutil, "rmtree", remove)
    if failure:
        with pytest.raises(PermissionError):
            manager.delete_model(engine, model_id, backend)
    else:
        assert manager.delete_model(engine, model_id, backend) == path
    if failure == "rename":
        assert sorted(p.name for p in path.iterdir()) == original_files
        assert len(manager.list_downloaded_models()) == 1
    else:
        assert not path.exists()
        assert manager.list_downloaded_models() == []


def test_delete_removes_both_modelscope_layouts(isolated_model_cache):
    manager = ModelDownloadManager()
    paths = manager._get_modelscope_model_dirs("iic/SenseVoiceSmall")
    for path in paths:
        _sensevoice_files(path)
    manager.delete_model("sensevoice", "iic/SenseVoiceSmall")
    assert all(not path.exists() for path in paths)
    assert manager.list_downloaded_models() == []


@pytest.mark.parametrize("outcome", ["success", "failure", "cancelled"])
@pytest.mark.parametrize("legacy", [True, False])
def test_modelscope_marker_tracks_sdk_completion(monkeypatch, isolated_model_cache, outcome, legacy):
    import asyncio
    from threading import Event

    manager = ModelDownloadManager()
    model_id = "iic/SenseVoiceSmall"
    paths = manager._get_modelscope_model_dirs(model_id)
    path = paths[1 if legacy else 0]
    marker = manager._get_modelscope_download_marker(model_id)
    event = Event()
    def download(*args, **kwargs):
        assert marker.is_file()
        _sensevoice_files(path)
        assert manager.list_downloaded_models() == []
        if outcome == "failure":
            raise RuntimeError("SDK failed")
        if outcome == "cancelled":
            event.set()
    monkeypatch.setattr(manager, "_resolve_sensevoice_download_python", lambda event: "fake-python")
    monkeypatch.setattr(manager, "_run_download_process", download)
    call = manager._download_sensevoice_from_modelscope("test", model_id, event)
    if outcome == "success":
        asyncio.run(call)
        assert not marker.exists()
        assert len(manager.list_downloaded_models()) == 1
    else:
        with pytest.raises(RuntimeError if outcome == "failure" else InterruptedError):
            asyncio.run(call)
        if outcome == "cancelled":
            # The SDK finished before the cancel was seen, so the complete model
            # must stay visible instead of being hidden by a stale marker.
            assert not marker.exists()
            assert len(manager.list_downloaded_models()) == 1
            return
        assert marker.is_file()
        assert manager.list_downloaded_models() == []
        # The on-disk marker must also survive a backend restart.
        assert ModelDownloadManager().list_downloaded_models() == []
        # A successful retry clears the marker and restores visibility.
        event.clear()
        monkeypatch.setattr(manager, "_run_download_process", lambda *args, **kwargs: None)
        asyncio.run(manager._download_sensevoice_from_modelscope("retry", model_id, event))
        assert not marker.exists()
        assert len(manager.list_downloaded_models()) == 1



def test_modelscope_success_clears_marker_before_post_download_cancellation(monkeypatch, isolated_model_cache):
    import asyncio
    from threading import Event

    manager = ModelDownloadManager()
    model_id = "iic/SenseVoiceSmall"
    event = Event()
    marker = manager._get_modelscope_download_marker(model_id)

    def complete_then_cancel(*args, **kwargs):
        event.set()

    monkeypatch.setattr(manager, "_resolve_sensevoice_download_python", lambda event: "fake-python")
    monkeypatch.setattr(manager, "_run_download_process", complete_then_cancel)

    with pytest.raises(InterruptedError):
        asyncio.run(manager._download_sensevoice_from_modelscope("test", model_id, event))

    assert not marker.exists()


def test_delete_clears_modelscope_in_progress_marker(isolated_model_cache):
    manager = ModelDownloadManager()
    model_id = "iic/SenseVoiceSmall"
    path = manager._get_modelscope_model_dir(model_id)
    _sensevoice_files(path)
    marker = manager._get_modelscope_download_marker(model_id)
    marker.parent.mkdir(parents=True)
    marker.touch()
    manager.delete_model("sensevoice", model_id)
    assert not marker.exists()
    assert not path.exists()
