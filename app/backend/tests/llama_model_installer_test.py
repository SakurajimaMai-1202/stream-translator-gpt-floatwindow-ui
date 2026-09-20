import hashlib

from backend.core import llama_model_installer as models


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
