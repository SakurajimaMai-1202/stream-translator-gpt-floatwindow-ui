import asyncio
import hashlib
import io
import json
import sys
import types

import pytest

from backend.core import llama_model_installer as models


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    # Do not read or alter the developer's config.yaml.
    monkeypatch.setitem(sys.modules, "backend.api.config", types.SimpleNamespace(_read_config=lambda: {}))


def mock_metadata(monkeypatch, names, digest="a" * 64, size=123):
    siblings = [{"rfilename": name, "lfs": {"sha256": digest, "size": size}} for name in names]
    requested = []

    def urlopen(request, timeout):
        requested.append(request.full_url)
        return _Response(json.dumps({"siblings": siblings}).encode())

    monkeypatch.setattr(models.urllib.request, "urlopen", urlopen)
    return requested


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_metadata_requests_blob_details_and_returns_verified_asset(monkeypatch):
    filename = models.MODELS["hy-mt2-q6-k"]
    expected = "a" * 64
    payload = json.dumps({
        "siblings": [{
            "rfilename": filename,
            "size": 123,
            "lfs": {"sha256": expected, "size": 456},
        }],
    }).encode()
    requested = {}

    def urlopen(request, timeout):
        requested["url"] = request.full_url
        requested["timeout"] = timeout
        return _Response(payload)

    monkeypatch.setattr(models.urllib.request, "urlopen", urlopen)

    url, size, digest = models.LlamaModelInstaller._metadata(filename)

    assert requested == {
        "url": f"https://huggingface.co/api/models/{models.REPOSITORY}?blobs=true",
        "timeout": 30,
    }
    assert url.endswith("/resolve/main/Hy-MT2-7B-Q6_K.gguf")
    assert size == 456
    assert digest == expected


def test_installer_downloads_verifies_and_activates_model(tmp_path, monkeypatch):
    payload = b"verified gguf"
    expected = hashlib.sha256(payload).hexdigest()
    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(installer, "_metadata", lambda _filename: ("https://example.invalid/model", len(payload), expected))

    def download(_self, _url, target):
        target.write_bytes(payload)

    monkeypatch.setattr(models.HttpDownloader, "download", download)
    job_id = installer.begin("hy-mt2-iq3-xxs")
    installer.install(job_id, "hy-mt2-iq3-xxs")

    status = installer.status()
    assert status["state"] == "completed"
    assert status["sha256"] == expected
    assert (tmp_path / models.MODELS["hy-mt2-iq3-xxs"]).read_bytes() == payload


def test_installer_rejects_bad_hash_and_removes_partial_file(tmp_path, monkeypatch):
    payload = b"corrupt gguf"
    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(installer, "_metadata", lambda _filename: ("https://example.invalid/model", len(payload), "0" * 64))

    def download(_self, _url, target):
        target.write_bytes(payload)

    monkeypatch.setattr(models.HttpDownloader, "download", download)
    job_id = installer.begin("hy-mt2-iq3-xxs")
    installer.install(job_id, "hy-mt2-iq3-xxs")

    status = installer.status()
    assert status["state"] == "error"
    assert "SHA-256" in status["error"]
    assert not (tmp_path / (models.MODELS["hy-mt2-iq3-xxs"] + ".part")).exists()
    assert installer.begin("hy-mt2-iq3-xxs") != job_id


@pytest.mark.parametrize("quant,names,expected", [
    ("Q4_K_M", ["model-q4_k_m.GGUF", "mmproj-Q4_K_M.gguf", "model-Q4_K_M.txt"], "model-q4_k_m.GGUF"),
    ("Q4_K", ["model-Q4_K_M.gguf", "model-Q4_K.gguf"], "model-Q4_K.gguf"),
    ("Q4_K", ["model-IQ4_K.gguf", "model-Q4_K-extra.gguf"], "model-Q4_K-extra.gguf"),
    ("UD-Q4_K_XL", ["sub/model-UD-Q4_K_XL.gguf"], "sub/model-UD-Q4_K_XL.gguf"),
])
def test_quant_resolution(monkeypatch, quant, names, expected):
    requested = mock_metadata(monkeypatch, names)
    filename, url, size, digest = models.LlamaModelInstaller._resolve("owner/repo", quant)
    assert filename == expected
    assert url == f"https://huggingface.co/owner/repo/resolve/main/{expected}"
    assert (size, digest) == (123, "a" * 64)
    assert requested == ["https://huggingface.co/api/models/owner/repo?blobs=true"]


@pytest.mark.parametrize("names,message", [
    (["one-Q4_K.gguf", "two-Q4_K.gguf"], "找到多個"),
    (["model-Q4_K_M.gguf", "mmproj-Q4_K.gguf"], "找不到"),
    (["model-Q4_K-00001-of-00002.gguf", "model-Q4_K-00002-of-00002.gguf"], "尚不支援分割模型檔案"),
])
def test_quant_resolution_refuses_unusable_matches(monkeypatch, names, message):
    mock_metadata(monkeypatch, names)
    with pytest.raises(RuntimeError, match=message):
        models.LlamaModelInstaller._resolve("owner/repo", "Q4_K")


@pytest.mark.parametrize("digest,size", [(None, 123), ("g" * 64, 123), ("a" * 63, 123), ("a" * 64, None)])
def test_unverified_metadata_never_downloaded(tmp_path, monkeypatch, digest, size):
    mock_metadata(monkeypatch, ["model-Q4_K_M.gguf"], digest=digest, size=size)
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(models.HttpDownloader, "download", lambda *args: pytest.fail("unverified download"))
    installer = models.LlamaModelInstaller()
    job = installer.begin("index-translate-2b")
    installer.install(job, "index-translate-2b")
    assert installer.status()["state"] == "error"
    assert "SHA-256" in installer.status()["error"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("catalog", models.MODEL_CATALOG, ids=lambda model: model["id"])
@pytest.mark.parametrize("choice", ["default", "minimum"])
def test_catalog_install_and_completed_parameters(tmp_path, monkeypatch, catalog, choice):
    quant = "" if choice == "default" else catalog["minimum_quant"]
    expected_quant = models._quant_token(quant or catalog["recommended_quant"])
    filename = f"model-{expected_quant}.gguf"
    payload = b"verified catalog gguf"
    requested = mock_metadata(monkeypatch, [filename], hashlib.sha256(payload).hexdigest(), len(payload))
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(models.HttpDownloader, "download", lambda self, url, path: path.write_bytes(payload))
    installer = models.LlamaModelInstaller()
    job = installer.begin(catalog["id"], quant)
    installer.install(job, catalog["id"])
    status = installer.status()
    assert status["state"] == "completed"
    assert status["catalog_id"] == catalog["id"]
    assert status["quant"] == expected_quant
    assert status["deployment_config"] == catalog["deployment_config"]
    assert (tmp_path / filename).read_bytes() == payload
    assert requested == [f"https://huggingface.co/api/models/{catalog['repo']}?blobs=true"]
    # A verified existing model completes without downloading again.
    monkeypatch.setattr(models.HttpDownloader, "download", lambda *args: pytest.fail("already verified"))
    job = installer.begin(catalog["id"], quant)
    installer.install(job, catalog["id"])
    assert installer.status()["deployment_config"] == catalog["deployment_config"]


def test_bad_quant_and_unknown_model_rejected():
    installer = models.LlamaModelInstaller()
    for model_id, quant in [("index-translate-2b", "Q8_0"), ("unknown", "")]:
        with pytest.raises(RuntimeError):
            installer.begin(model_id, quant)
    assert installer.status()["state"] == "idle"


@pytest.mark.parametrize("model_id,filename", models.MODELS.items())
def test_legacy_ids_keep_exact_files(tmp_path, monkeypatch, model_id, filename):
    payload = b"legacy gguf"
    configured = tmp_path / "configured"
    configured.mkdir()
    monkeypatch.setattr(sys.modules["backend.api.config"], "_read_config",
                        lambda: {"llama": {"model_dir": str(configured)}})
    mock_metadata(monkeypatch, [filename], hashlib.sha256(payload).hexdigest(), len(payload))
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(models.HttpDownloader, "download", lambda self, url, path: path.write_bytes(payload))
    installer = models.LlamaModelInstaller()
    job = installer.begin(model_id)
    installer.install(job, model_id)
    status = installer.status()
    assert status["state"] == "completed"
    assert status["filename"] == filename
    assert status["catalog_id"] == ""
    assert status["deployment_config"] == {}
    assert status["path"] == str(tmp_path / filename)
    assert (tmp_path / filename).read_bytes() == payload
    assert not list(configured.iterdir())


@pytest.mark.parametrize("setting", ["absolute", "relative", "missing", "file", "empty"])
def test_model_directory(tmp_path, monkeypatch, setting):
    configured = tmp_path / "configured"
    configured.mkdir()
    file_path = tmp_path / "file"
    file_path.write_text("not a directory")
    raw = {"absolute": str(configured), "relative": "configured", "missing": str(tmp_path / "missing"),
           "file": str(file_path), "empty": ""}[setting]
    monkeypatch.setattr(sys.modules["backend.api.config"], "_read_config", lambda: {"llama": {"model_dir": raw}})
    monkeypatch.setattr(models, "get_app_root", lambda: tmp_path)
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(models, "simple_model_directory", lambda: fallback)
    assert models.model_directory() == (configured if setting in {"absolute", "relative"} else fallback)


def test_cancel_preserves_resumable_partial_and_new_job(tmp_path, monkeypatch):
    payload = b"verified gguf"
    model_id = "hy-mt2-iq3-xxs"
    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(installer, "_metadata", lambda filename: ("url", len(payload), hashlib.sha256(payload).hexdigest()))
    next_job = []

    def cancel_download(downloader, url, partial):
        partial.write_bytes(payload[:4])
        downloader._progress(4, len(payload))
        assert installer.status()["progress"] > 0.0
        assert installer.status()["bytes_downloaded"] == 4
        status = installer.cancel()
        assert status["state"] == "cancelled"
        assert status["progress"] == 0.0
        assert status["bytes_downloaded"] == 0
        downloader._progress(8, len(payload))
        assert installer.status() == status
        assert status["message"] == "已取消下載"
        assert downloader._cancel.is_set()
        next_job.append(installer.begin(model_id))
        downloader._progress(100, 100)  # Late progress must not corrupt the new job.
        raise InterruptedError()

    monkeypatch.setattr(models.HttpDownloader, "download", cancel_download)
    job = installer.begin(model_id)
    with pytest.raises(RuntimeError):
        installer.begin(model_id)
    installer.install(job, model_id)
    assert installer.status()["job_id"] == next_job[0]
    assert installer.status()["state"] == "resolving"
    assert installer.status()["bytes_downloaded"] == 0
    partial = tmp_path / (models.MODELS[model_id] + ".part")
    assert partial.read_bytes() == payload[:4]

    def resume(downloader, url, path):
        assert not downloader._cancel.is_set()
        assert path.read_bytes() == payload[:4]
        path.write_bytes(payload)

    monkeypatch.setattr(models.HttpDownloader, "download", resume)
    installer.install(next_job[0], model_id)
    assert installer.status()["state"] == "completed"
    assert not partial.exists()


def test_cancel_before_worker_starts(monkeypatch):
    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(installer, "_metadata", lambda *args: pytest.fail("cancelled metadata"))
    job = installer.begin("hy-mt2-q6-k")
    installer.cancel()
    installer.install(job, "hy-mt2-q6-k")
    assert installer.status()["state"] == "cancelled"
    assert installer.begin("hy-mt2-q6-k") != job


def test_cancel_during_verification_does_not_activate(tmp_path, monkeypatch):
    installer = models.LlamaModelInstaller()
    model_id = "hy-mt2-q6-k"
    payload = b"gguf"
    expected = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(installer, "_metadata", lambda filename: ("url", len(payload), expected))
    monkeypatch.setattr(models.HttpDownloader, "download", lambda self, url, path: path.write_bytes(payload))

    def cancelled_hash(path, cancel):
        installer.cancel()
        return expected

    monkeypatch.setattr(installer, "_sha256", cancelled_hash)
    job = installer.begin(model_id)
    installer.install(job, model_id)
    assert installer.status()["state"] == "cancelled"
    assert not (tmp_path / models.MODELS[model_id]).exists()
    assert (tmp_path / (models.MODELS[model_id] + ".part")).read_bytes() == payload


def test_install_route_passes_quant_to_installer(monkeypatch):
    from backend.api import llama

    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(llama, "model_installer", installer)
    background_tasks = llama.BackgroundTasks()
    calls = []
    original_begin = installer.begin

    def begin(model_id, quant=""):
        calls.append((model_id, quant))
        return original_begin(model_id, quant)

    monkeypatch.setattr(installer, "begin", begin)
    catalog = models.MODEL_CATALOG[0]
    quant = models._quant_token(catalog["minimum_quant"])
    result = asyncio.run(llama.install_model(
        llama.ModelInstallRequest(model_id=catalog["id"], quant=quant), background_tasks))

    assert calls == [(catalog["id"], quant)]
    assert result["success"] is True
    assert result["job_id"] == installer.status()["job_id"]
    assert installer.status()["quant"] == quant
    assert len(background_tasks.tasks) == 1
    task = background_tasks.tasks[0]
    assert task.func == installer.install
    assert task.args == (result["job_id"], catalog["id"])


def test_cancel_route_cancels_running_job(monkeypatch):
    from backend.api import llama

    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(llama, "model_installer", installer)
    job = installer.begin("hy-mt2-q6-k")
    installer._set(job, state="downloading", progress=0.5, bytes_downloaded=50, bytes_total=100)

    result = asyncio.run(llama.cancel_model_install())

    assert result == installer.status()
    assert result["job_id"] == job
    assert result["state"] == "cancelled"
    assert result["progress"] == 0.0
    assert result["bytes_downloaded"] == 0
    assert installer._cancel.is_set()


@pytest.mark.parametrize("body", ["matching", "empty", "stale"])
def test_cancel_route_optional_job_id(monkeypatch, body):
    from backend.api import llama

    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(llama, "model_installer", installer)
    job = installer.begin("hy-mt2-q6-k")
    before = installer.status()
    request = llama.ModelInstallCancelRequest(**({} if body == "empty" else {
        "job_id": job if body == "matching" else "old-job"}))
    if body == "stale":
        with pytest.raises(llama.HTTPException) as error:
            asyncio.run(llama.cancel_model_install(request))
        assert error.value.status_code == 409
        assert error.value.detail == "\u4e0b\u8f09\u5de5\u4f5c\u5df2\u8b8a\u66f4\uff0c\u8acb\u91cd\u65b0\u6574\u7406"
        assert installer.status() == before
        assert not installer._cancel.is_set()
    else:
        assert asyncio.run(llama.cancel_model_install(request))["state"] == "cancelled"
        assert installer._cancel.is_set()


@pytest.mark.parametrize("filename", ["../model-Q4_K_M.gguf", "sub/model-Q4_K_M.gguf",
    "sub\\model-Q4_K_M.gguf", "model Q4_K_M.gguf", "model:Q4_K_M.gguf", "model-Q4_K_M.GGUF",
    "model-Q4_K_M.gguf\n"])
def test_unsafe_resolved_filename_never_downloads(tmp_path, monkeypatch, filename):
    installer = models.LlamaModelInstaller()
    monkeypatch.setattr(installer, "_resolve", lambda *a: (filename, "url", 4, "a" * 64))
    monkeypatch.setattr(models, "model_directory", lambda: tmp_path)
    monkeypatch.setattr(models.HttpDownloader, "download", lambda *a: pytest.fail("unsafe download"))
    job = installer.begin("index-translate-2b")
    installer.install(job, "index-translate-2b")
    assert installer.status()["state"] == "error"
    assert "\u6a94\u540d\u4e0d\u5b89\u5168" in installer.status()["error"]
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("old_payload", [b"different size", b"bad!"])
def test_existing_mismatched_file_is_preserved(tmp_path, monkeypatch, old_payload):
    payload = b"gguf"
    digest = hashlib.sha256(payload).hexdigest()
    installer = models.LlamaModelInstaller()
    model_id = "hy-mt2-q6-k"
    target = tmp_path / models.MODELS[model_id]
    target.write_bytes(old_payload)
    alternate = target.with_name(f"{target.stem}.{digest[:8]}.gguf")
    monkeypatch.setattr(models, "simple_model_directory", lambda: tmp_path)
    monkeypatch.setattr(installer, "_metadata", lambda *a: ("url", len(payload), digest))
    monkeypatch.setattr(models.HttpDownloader, "download", lambda self, url, path: path.write_bytes(payload))
    job = installer.begin(model_id)
    installer.install(job, model_id)
    assert target.read_bytes() == old_payload
    assert alternate.read_bytes() == payload
    assert installer.status()["path"] == str(alternate)
    assert installer.status()["filename"] == alternate.name
    assert installer.status()["state"] == "completed"
    monkeypatch.setattr(models.HttpDownloader, "download", lambda *a: pytest.fail("verified alternate"))
    installer.install(installer.begin(model_id), model_id)
    assert installer.status()["state"] == "completed"
    alternate.write_bytes(b"another file")
    installer.install(installer.begin(model_id), model_id)
    assert installer.status()["state"] == "error"
    assert alternate.read_bytes() == b"another file"
    assert target.read_bytes() == old_payload


def test_status_directory_uses_fallback_for_stale_config(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.modules["backend.api.config"], "_read_config",
                        lambda: {"llama": {"model_dir": str(tmp_path / "missing")}})
    fallback = tmp_path / "fallback"
    monkeypatch.setattr(models, "simple_model_directory", lambda: fallback)
    installer = models.LlamaModelInstaller()
    payload = b"gguf"
    monkeypatch.setattr(installer, "_resolve", lambda *a: (
        "model-Q4_K_M.gguf", "url", len(payload), hashlib.sha256(payload).hexdigest()))

    def download(self, url, path):
        assert installer.status()["directory"] == str(fallback)
        assert installer.status()["state"] == "downloading"
        path.write_bytes(payload)

    monkeypatch.setattr(models.HttpDownloader, "download", download)
    job = installer.begin("index-translate-2b")
    installer.install(job, "index-translate-2b")
    assert installer.status()["state"] == "completed"
    assert installer.status()["directory"] == str(fallback)
    assert installer.status()["path"] == str(fallback / "model-Q4_K_M.gguf")
