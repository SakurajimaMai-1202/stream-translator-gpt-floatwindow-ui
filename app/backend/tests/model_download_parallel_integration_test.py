import asyncio
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

from backend.core import model_download_manager as module


def test_cpu_archive_uses_shared_downloader_and_extracts(monkeypatch, tmp_path):
    manager = module.ModelDownloadManager()
    monkeypatch.setattr(module, 'ensure_model_storage', lambda: tmp_path)
    monkeypatch.setitem(module.SHERPA_CPU_BUNDLES, 'fixture', ('test-model', ('model.onnx',)))
    calls = []

    def download(self, url, destination):
        calls.append((url, destination))
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(destination, 'w:bz2') as archive:
            member = tarfile.TarInfo('test-model/model.onnx')
            member.size = 5
            archive.addfile(member, io.BytesIO(b'model'))

    monkeypatch.setattr(module.HttpDownloader, 'download', download)
    asyncio.run(manager._download_sherpa_archive('task', 'fixture'))
    assert calls[0][1].name.endswith('.part')
    assert (tmp_path / 'sherpa-onnx/test-model/model.onnx').read_bytes() == b'model'


def test_hf_prefetch_precedes_native_snapshot(monkeypatch, tmp_path):
    import huggingface_hub
    calls = []
    info = SimpleNamespace(sha='a' * 40, siblings=[])
    monkeypatch.setattr(module, 'get_huggingface_hub_cache', lambda: tmp_path)
    monkeypatch.setattr(huggingface_hub, 'HfApi', lambda: SimpleNamespace(model_info=lambda *a, **k: info))
    monkeypatch.setattr(module, 'prefetch_large_files', lambda *a: calls.append('prefetch'))

    def snapshot(**kwargs):
        calls.append('snapshot')
        assert kwargs['max_workers'] == 4
        assert kwargs['cache_dir'] == str(tmp_path)
        return str(tmp_path)

    monkeypatch.setattr(huggingface_hub, 'snapshot_download', snapshot)
    asyncio.run(module.ModelDownloadManager()._download_from_hf('task', 'test/model'))
    assert calls == ['prefetch', 'snapshot']


def test_modelscope_subprocess_enables_range_downloads(monkeypatch, tmp_path):
    manager = module.ModelDownloadManager()
    monkeypatch.setattr(manager, '_get_modelscope_cache_dir', lambda: tmp_path)
    monkeypatch.setattr(manager, '_resolve_sensevoice_download_python', lambda: 'python')

    def run(*args, **kwargs):
        env = kwargs['env']
        assert env['MODELSCOPE_DOWNLOAD_PARALLEL_WORKERS'] == '4'
        assert env['MODELSCOPE_DOWNLOAD_PARALLEL_THRESHOLD_MB'] == '16'
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(module.subprocess, 'run', run)
    asyncio.run(manager._download_sensevoice_from_modelscope('task', 'iic/SenseVoiceSmall'))
