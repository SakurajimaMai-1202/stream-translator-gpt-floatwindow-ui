import hashlib
from types import SimpleNamespace
from unittest import mock

import pytest
import huggingface_hub
from huggingface_hub import HfFileMetadata

from cpu_asr_sidecar_manager_test import range_server
from backend.core import hf_parallel_download as hf
from backend.core import http_downloader as http


def model_info(payload, digest=None):
    return SimpleNamespace(sha='a' * 40, siblings=[SimpleNamespace(
        rfilename='model.bin', size=len(payload),
        lfs=SimpleNamespace(sha256=digest or hashlib.sha256(payload).hexdigest()),
    )])


def test_parallel_blob_is_reused_by_real_huggingface_sdk(tmp_path, monkeypatch):
    with range_server() as (url, payload, stats):
        info = model_info(payload)
        digest = info.siblings[0].lfs.sha256
        monkeypatch.setattr(hf, 'DOWNLOAD_CHUNK_SIZE', 8192)
        monkeypatch.setattr(http, 'DOWNLOAD_CHUNK_SIZE', 8192)
        monkeypatch.setattr(huggingface_hub, 'hf_hub_url', lambda *a, **kw: url)
        hf.prefetch_large_files('test/model', info, tmp_path)
        assert stats['peak'] > 1
        calls = len(stats['ranges'])
        metadata = HfFileMetadata(commit_hash=info.sha, etag=digest, location=url, size=len(payload),
                                 xet_file_data=None)
        with mock.patch('huggingface_hub.file_download.get_hf_file_metadata', return_value=metadata):
            result = huggingface_hub.hf_hub_download('test/model', 'model.bin',
                                                   revision=info.sha, cache_dir=tmp_path)
        from pathlib import Path
        assert Path(result).read_bytes() == payload
        assert len(stats['ranges']) == calls
        hf.prefetch_large_files('test/model', info, tmp_path)
        assert len(stats['ranges']) == calls


def test_corrupt_blob_never_enters_hf_cache(tmp_path, monkeypatch):
    with range_server() as (url, payload, _):
        monkeypatch.setattr(hf, 'DOWNLOAD_CHUNK_SIZE', 8192)
        monkeypatch.setattr(http, 'DOWNLOAD_CHUNK_SIZE', 8192)
        monkeypatch.setattr(huggingface_hub, 'hf_hub_url', lambda *a, **kw: url)
        with pytest.raises(RuntimeError, match='integrity'):
            hf.prefetch_large_files('test/model', model_info(payload, '0' * 64), tmp_path)
        assert not list((tmp_path / 'models--test--model' / 'blobs').iterdir())


def test_private_download_falls_back_without_writing_completed_blob(tmp_path, monkeypatch):
    import urllib.error
    monkeypatch.setattr(hf, 'DOWNLOAD_CHUNK_SIZE', 1)
    with mock.patch.object(http.HttpDownloader, 'download', side_effect=urllib.error.HTTPError(
            'https://example.test', 401, 'Unauthorized', {}, None)):
        hf.prefetch_large_files('test/model', model_info(b'private model'), tmp_path)
    assert not list((tmp_path / 'models--test--model' / 'blobs').iterdir())
