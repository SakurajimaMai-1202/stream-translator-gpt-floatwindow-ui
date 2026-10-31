import asyncio
import io
import tarfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace

from backend.core import model_download_manager as module


def test_cpu_archive_uses_shared_downloader_and_extracts(monkeypatch, tmp_path):
    manager = module.ModelDownloadManager()
    monkeypatch.setattr(module, 'ensure_model_storage', lambda: tmp_path)
    monkeypatch.setitem(module.SHERPA_CPU_BUNDLES, 'fixture', ('test-model', ('model.onnx',)))
    calls = []
    cancel_event = Event()

    def download(self, url, destination):
        assert self._cancel is cancel_event
        calls.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(destination, 'w:bz2') as archive:
            member = tarfile.TarInfo('test-model/model.onnx')
            member.size = 5
            archive.addfile(member, io.BytesIO(b'model'))

    monkeypatch.setattr(module.HttpDownloader, 'download', download)
    asyncio.run(manager._download_sherpa_archive('task', 'fixture', cancel_event))
    assert calls[0][1].name.endswith('.part')
    assert (tmp_path / 'sherpa-onnx/test-model/model.onnx').read_bytes() == b'model'


def test_hf_prefetch_precedes_native_snapshot(monkeypatch, tmp_path):
    import huggingface_hub
    calls = []
    info = SimpleNamespace(sha='a' * 40, siblings=[])
    monkeypatch.setattr(module, 'get_huggingface_hub_cache', lambda: tmp_path)
    monkeypatch.setattr(huggingface_hub, 'HfApi', lambda: SimpleNamespace(model_info=lambda *a, **k: info))
    event = Event()

    def prefetch(*args, cancel_event):
        assert cancel_event is event
        calls.append('prefetch')

    monkeypatch.setattr(module, 'prefetch_large_files', prefetch)

    def snapshot(**kwargs):
        calls.append('snapshot')
        assert kwargs['max_workers'] == 4
        assert kwargs['cache_dir'] == str(tmp_path)
        return str(tmp_path)

    monkeypatch.setattr(huggingface_hub, 'snapshot_download', snapshot)
    asyncio.run(module.ModelDownloadManager()._download_from_hf('task', 'test/model', event))
    assert calls == ['prefetch', 'snapshot']


def test_modelscope_subprocess_enables_range_downloads(monkeypatch, tmp_path):
    manager = module.ModelDownloadManager()
    monkeypatch.setattr(manager, '_get_modelscope_cache_dir', lambda: tmp_path)
    cancel_event = Event()
    monkeypatch.setattr(manager, '_resolve_sensevoice_download_python', lambda event: 'python')

    def popen(*args, **kwargs):
        env = kwargs['env']
        assert env['MODELSCOPE_DOWNLOAD_PARALLEL_WORKERS'] == '4'
        assert env['MODELSCOPE_DOWNLOAD_PARALLELS'] == '4'
        assert env['MODELSCOPE_DOWNLOAD_PARALLEL_THRESHOLD_MB'] == '16'
        return SimpleNamespace(returncode=0, poll=lambda: 0)

    monkeypatch.setattr(module.subprocess, 'Popen', popen)
    asyncio.run(manager._download_sensevoice_from_modelscope('task', 'iic/SenseVoiceSmall', cancel_event))


# Small synthetic payloads exercise the production verification/publication path.
def _haas_fixture(monkeypatch, tmp_path):
    import hashlib
    manager = module.ModelDownloadManager()
    monkeypatch.setattr(module, "ensure_model_storage", lambda: tmp_path)
    monkeypatch.setattr(module, "get_model_storage_root", lambda: tmp_path)
    monkeypatch.setattr(manager, "_get_hf_cache_dir", lambda: tmp_path / "hub")
    monkeypatch.setattr(manager, "_get_modelscope_cache_dir", lambda: tmp_path / "modelscope")
    payloads = {name: name.encode() for name, _, _ in module.HAAS_PINNED_FILES}
    monkeypatch.setattr(module, "HAAS_PINNED_FILES", tuple(
        (name, len(data), hashlib.sha256(data).hexdigest()) for name, data in payloads.items()))
    target = tmp_path / "sherpa-onnx" / module.SHERPA_CPU_BUNDLES[module.HAAS_MODEL_ID][0]
    return manager, payloads, target


def test_haas_atomic_verified_install_and_progress(monkeypatch, tmp_path):
    manager, payloads, target = _haas_fixture(monkeypatch, tmp_path)
    event = Event()
    progress = []
    monkeypatch.setattr(manager, "_update_byte_progress", lambda *args: progress.append(args))
    def download(self, url, destination):
        assert not target.exists()
        assert not any(m.model_id == module.HAAS_MODEL_ID for m in manager.list_downloaded_models())
        assert self._cancel is event
        assert f"/resolve/{module.HAAS_REVISION}/" in url
        destination.write_bytes(payloads[destination.name])
        self._progress(len(payloads[destination.name]), len(payloads[destination.name]))
    monkeypatch.setattr(module.HttpDownloader, "download", download)
    asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, event))
    assert all((target / name).read_bytes() == data for name, data in payloads.items())
    assert progress[-1][1:3] == (sum(map(len, payloads.values())),) * 2
    assert any(m.model_id == module.HAAS_MODEL_ID for m in manager.list_downloaded_models())
    # Installed targets retain the existing early-return semantics.
    monkeypatch.setattr(module.HttpDownloader, "download", lambda *a: (_ for _ in ()).throw(AssertionError()))
    asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, event))
    manager.delete_model("parakeet-ctc-ja", module.HAAS_MODEL_ID, "cpu")
    assert not target.exists()


def test_haas_verification_failures_are_not_installed(monkeypatch, tmp_path):
    import pytest
    for failure in ("size", "SHA-256"):
        manager, payloads, target = _haas_fixture(monkeypatch, tmp_path / failure)
        def download(self, url, destination):
            data = payloads[destination.name]
            destination.write_bytes(data + b"x" if failure == "size" else b"x" * len(data))
        monkeypatch.setattr(module.HttpDownloader, "download", download)
        with pytest.raises(RuntimeError, match=failure):
            asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, Event()))
        assert not target.exists()
        assert not list(target.parent.glob(".*.partial/encoder.quantized.onnx"))
        assert not any(m.model_id == module.HAAS_MODEL_ID for m in manager.list_downloaded_models())


def test_haas_cancel_keeps_resumable_prefix_and_blocks_delete(monkeypatch, tmp_path):
    import pytest
    manager, payloads, target = _haas_fixture(monkeypatch, tmp_path)
    event = Event()
    def download(self, url, destination):
        destination.write_bytes(payloads[destination.name][:2])
        event.set()
        raise InterruptedError("cancelled")
    monkeypatch.setattr(module.HttpDownloader, "download", download)
    with pytest.raises(InterruptedError):
        asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, event))
    assert not target.exists()
    assert not any(m.model_id == module.HAAS_MODEL_ID for m in manager.list_downloaded_models())
    manager._model_workers[("cpu", module.HAAS_MODEL_ID)] = "task"
    with pytest.raises(ValueError, match="active"):
        manager.delete_model("parakeet-ctc-ja", module.HAAS_MODEL_ID, "cpu")
    manager._model_workers.clear()
    event.clear()
    def resume(self, url, destination):
        if destination.exists():
            assert destination.read_bytes() == payloads[destination.name][:2]
        destination.write_bytes(payloads[destination.name])
    monkeypatch.setattr(module.HttpDownloader, "download", resume)
    asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, event))
    assert target.is_dir()


def test_haas_cpu_only_and_pinned_registry_consistency():
    import pytest
    from stream_translator_gpt.sherpa_onnx_models import SHERPA_CPU_MODELS
    manager = module.ModelDownloadManager()
    assert manager._validate_model_id("parakeet-ctc-ja", module.HAAS_MODEL_ID, "cpu") == module.HAAS_MODEL_ID
    with pytest.raises(ValueError, match="only on CPU"):
        manager._validate_model_id("parakeet-ctc-ja", module.HAAS_MODEL_ID, "gpu")
    bundle, required = module.SHERPA_CPU_BUNDLES[module.HAAS_MODEL_ID]
    spec = SHERPA_CPU_MODELS[module.HAAS_MODEL_ID]
    assert (spec.bundle, spec.required_paths) == (bundle, required)
    assert set(required) <= {name for name, _, _ in module.HAAS_PINNED_FILES}
    assert {"LICENSE", "NOTICE"} <= {name for name, _, _ in module.HAAS_PINNED_FILES}


def test_haas_task_cancel_mid_download_never_publishes(monkeypatch, tmp_path):
    import pytest
    manager, payloads, target = _haas_fixture(monkeypatch, tmp_path)
    entered = Event()
    def download(self, url, destination):
        destination.write_bytes(payloads[destination.name][:2])
        entered.set()
        assert self._cancel.wait(3), "test never cancelled download"
        raise InterruptedError("cancelled")
    monkeypatch.setattr(module.HttpDownloader, "download", download)
    async def scenario():
        task_id = await manager.start_download("parakeet-ctc-ja", module.HAAS_MODEL_ID, "cpu")
        worker = manager._workers[task_id]
        assert await asyncio.to_thread(entered.wait, 3)
        staging = target.with_name(f".{target.name}.{module.HAAS_REVISION}.partial")
        assert staging.exists()
        with pytest.raises(ValueError, match="active"):
            manager.delete_model("parakeet-ctc-ja", module.HAAS_MODEL_ID, "cpu")
        assert (staging / "encoder.quantized.onnx").read_bytes() == payloads["encoder.quantized.onnx"][:2]
        manager.cancel(task_id)
        await asyncio.wait_for(worker, 3)
        assert manager.get_task(task_id).status == "cancelled"
    asyncio.run(scenario())
    assert not target.exists()
    assert not any(m.model_id == module.HAAS_MODEL_ID for m in manager.list_downloaded_models())



def test_haas_incomplete_target_recovers(monkeypatch, tmp_path):
    manager, payloads, target = _haas_fixture(monkeypatch, tmp_path)
    target.mkdir(parents=True)
    (target / "encoder.quantized.onnx").write_bytes(b"old encoder")
    (target / "obsolete").write_bytes(b"old content")

    def download(self, url, destination):
        destination.write_bytes(payloads[destination.name])

    monkeypatch.setattr(module.HttpDownloader, "download", download)
    asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, Event()))
    assert {p.name for p in target.iterdir()} == set(payloads)
    assert all((target / name).read_bytes() == data for name, data in payloads.items())
    assert not list(target.parent.glob(".deleted-*"))
    assert not target.with_name(f".{target.name}.{module.HAAS_REVISION}.partial").exists()


def test_haas_failed_publication_restores_incomplete_target(monkeypatch, tmp_path):
    import pytest
    manager, payloads, target = _haas_fixture(monkeypatch, tmp_path)
    target.mkdir(parents=True)
    (target / "encoder.quantized.onnx").write_bytes(b"old encoder")
    staging = target.with_name(f".{target.name}.{module.HAAS_REVISION}.partial")
    original_rename = Path.rename

    def rename(path, destination):
        if path == staging:
            raise OSError("publication failed")
        return original_rename(path, destination)

    def download(self, url, destination):
        destination.write_bytes(payloads[destination.name])

    monkeypatch.setattr(module.HttpDownloader, "download", download)
    monkeypatch.setattr(Path, "rename", rename)
    with pytest.raises(OSError, match="publication failed"):
        asyncio.run(manager._download_sherpa_archive("task", module.HAAS_MODEL_ID, Event()))
    assert (target / "encoder.quantized.onnx").read_bytes() == b"old encoder"
    assert all((staging / name).read_bytes() == data for name, data in payloads.items())
    assert not list(target.parent.glob(".deleted-*"))


def test_haas_delete_removes_staging_with_or_without_final(monkeypatch, tmp_path):
    for with_final in (False, True):
        manager, payloads, target = _haas_fixture(monkeypatch, tmp_path / str(with_final))
        staging = target.with_name(f".{target.name}.{module.HAAS_REVISION}.partial")
        staging.mkdir(parents=True)
        (staging / "encoder.data").write_bytes(b"partial")
        if with_final:
            target.mkdir()
            for name, data in payloads.items():
                (target / name).write_bytes(data)
        manager.delete_model("parakeet-ctc-ja", module.HAAS_MODEL_ID, "cpu")
        assert not staging.exists()
        assert not target.exists()
        assert not list(target.parent.glob(".deleted-*"))
