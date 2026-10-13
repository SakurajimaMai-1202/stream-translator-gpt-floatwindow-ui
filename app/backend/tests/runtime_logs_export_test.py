import io
import json
import os
import sys
import threading
import zipfile
from types import ModuleType, SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import runtime
from backend.core.admin_auth import TOKEN_HEADER, register_admin_auth
from backend.core.config_secrets import SECRET_KEYS


TOKEN = "offline-admin-token"


@pytest.fixture
def export_client(monkeypatch, tmp_path):
    config = {"models": {"storage_path": "offline-models"}}
    worker_threads = []

    def get_config():
        worker_threads.append(threading.get_ident())
        return config

    monkeypatch.setattr(runtime, "get_config_manager", lambda: SimpleNamespace(get_config=get_config))
    monkeypatch.setattr(runtime, "resolve_log_dir", lambda: tmp_path)
    monkeypatch.setattr(runtime, "build_runtime_status", lambda config: {"profile": "offline"})
    monkeypatch.setattr(runtime, "cpu_asr_sidecar_manager", SimpleNamespace(status=lambda: {"state": "offline"}))
    llama = ModuleType("backend.api.llama")
    llama._get_llama_runtime_info = lambda: {"state": "offline"}
    monkeypatch.setitem(sys.modules, "backend.api.llama", llama)
    monkeypatch.setenv("FLOATWINDOW_ADMIN_TOKEN", TOKEN)
    app = FastAPI()
    register_admin_auth(app, "/api")
    app.include_router(runtime.router, prefix="/api")
    with TestClient(app) as client:
        yield client, config, tmp_path, worker_threads


def _export(client):
    response = client.get("/api/runtime/logs/export", headers={TOKEN_HEADER: TOKEN})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith('attachment; filename="stream-translator-logs-')
    assert response.headers["content-disposition"].endswith('.zip"')
    return zipfile.ZipFile(io.BytesIO(response.content))


def test_zip_contains_logs_diagnostics_and_readme(export_client):
    client, _, directory, threads = export_client
    (directory / "backend.log").write_text("backend log", encoding="utf-8")
    (directory / "backend.log.5").write_bytes(b"older log \xff")
    (directory / "ignored.txt").write_text("not a log", encoding="utf-8")
    (directory / "backend.log.bad").write_text("not a numbered backup", encoding="utf-8")
    with _export(client) as archive:
        assert set(archive.namelist()) == {
            "logs/backend.log", "logs/backend.log.5", "diagnostics.json", "README.txt", "export-notes.txt",
        }
        report = client.get("/api/runtime/diagnostics", headers={TOKEN_HEADER: TOKEN}).json()
        assert json.loads(archive.read("diagnostics.json")) == report
        assert "遮蔽" in archive.read("README.txt").decode("utf-8")
        assert "\ufffd" in archive.read("logs/backend.log.5").decode("utf-8")
    assert threads and all(thread != threading.get_ident() for thread in threads)


def test_redacts_all_config_secrets_urls_and_query_parameters(export_client):
    client, config, directory, _ = export_client
    values = ["secret-value-" + name for name in sorted(SECRET_KEYS)]
    config["nested"] = {key: value for key, value in zip(sorted(SECRET_KEYS), values)}
    config["nested"]["cookies_by_site"] = {"youtube": "site-cookie-value", "other": "other-cookie-value"}
    config["elsewhere"] = {"access_token": "extra-token-value", "password": "password-value"}
    config["short"] = {"api_key": "abc"}
    config["models"]["storage_path"] = "https://user:pass@host/models?token=diagnostic-token"
    values.remove("secret-value-cookies_by_site")
    values += ["site-cookie-value", "other-cookie-value", "extra-token-value", "password-value"]
    urls = ["https://user:pass@host/path?Token=query-token&ok=keep", "socks5://user:pass@proxy:1080"]
    urls += ["https://host/?" + name + "=query-value" for name in ("key", "secret", "auth", "signature", "sig")]
    (directory / "app.log").write_text("\n".join(values + urls + ["abc"]), encoding="utf-8")
    with _export(client) as archive:
        text = archive.read("logs/app.log").decode("utf-8")
        for value in values + ["user:pass", "query-token", "query-value"]:
            assert value not in text
        assert "https://<redacted>@host/path?Token=<redacted>&ok=keep" in text
        assert "socks5://<redacted>@proxy:1080" in text
        assert "abc" in text
        assert "<redacted>" in text
        diagnostic = archive.read("diagnostics.json").decode("utf-8")
        assert "user:pass" not in diagnostic and "diagnostic-token" not in diagnostic


def test_size_cap_keeps_newest_and_tail_of_partial_file(export_client, monkeypatch):
    client, _, directory, _ = export_client
    monkeypatch.setattr(runtime, "LOG_EXPORT_MAX_BYTES", 3200)
    payloads = {"new.log": b"N" * 100, "partial.log.1": b"HEAD" + b"P" * 6000 + b"\n" + b"TAIL", "old.log.5": b"OLD"}
    for index, (name, content) in enumerate(payloads.items()):
        path = directory / name
        path.write_bytes(content)
        os.utime(path, (300 - index, 300 - index))
    with _export(client) as archive:
        assert sum(info.file_size for info in archive.infolist()) <= 3200
        logs = [name for name in archive.namelist() if name.startswith("logs/")]
        assert logs == ["logs/new.log", "logs/partial.log.1"]
        assert archive.read(logs[0]) == payloads["new.log"]
        tail = archive.read(logs[1])
        assert 0 < len(tail) < len(payloads["partial.log.1"])
        assert payloads["partial.log.1"].endswith(tail) and tail.endswith(b"TAIL")
        notes = archive.read("export-notes.txt").decode("utf-8")
        assert "截斷：partial.log.1" in notes and "略過：old.log.5" in notes


@pytest.mark.parametrize("path", ["/api/runtime/logs/export", "/api/runtime/diagnostics"])
@pytest.mark.parametrize("headers", [{}, {TOKEN_HEADER: "wrong-token"}])
def test_export_requires_same_admin_token_as_diagnostics(export_client, path, headers):
    client, _, _, threads = export_client
    assert client.get(path, headers=headers).status_code == 401
    assert not threads


def test_empty_log_directory_still_exports_diagnostics(export_client):
    client, _, _, _ = export_client
    with _export(client) as archive:
        assert set(archive.namelist()) == {"diagnostics.json", "README.txt", "export-notes.txt"}


@pytest.mark.parametrize("line,secret", [
    ("Authorization: Bearer old-key", "old-key"),
    ("authorization: Basic b2xkOnBhc3M=", "b2xkOnBhc3M="),
    ('"Authorization": "Bearer old-json-key"', "old-json-key"),
    ("Cookie: session=old-cookie; other=another-cookie", "old-cookie"),
    ("Set-Cookie: session=old-set-cookie; Path=/; HttpOnly", "old-set-cookie"),
    ("https://host/?access_token=old-access-token&ok=keep", "old-access-token"),
    ("https://host/?api_key=old-api-key&ok=keep", "old-api-key"),
    ("https://host/?APIKEY=old-apikey&ok=keep", "old-apikey"),
    ("https://host/?x-api-key=old-x-key&ok=keep", "old-x-key"),
    ("https://host/?user_password=old-password&ok=keep", "old-password"),
    ("https://host/?request_signature=old-signature&ok=keep", "old-signature"),
    ("api_key=rotated-field-key", "rotated-field-key"),
    ("x-api-key: rotated-header-key", "rotated-header-key"),
    ('"token": "rotated-json-token"', "rotated-json-token"),
    ("password='rotated password with spaces'", "rotated password with spaces"),
    ("client_secret: rotated-client-secret", "rotated-client-secret"),
])
def test_redacts_old_credentials_by_pattern_without_config_values(export_client, line, secret):
    client, _, directory, _ = export_client
    (directory / "backend.log.1").write_text(line, encoding="utf-8")
    with _export(client) as archive:
        text = archive.read("logs/backend.log.1").decode("utf-8")
        assert secret not in text
        assert "<redacted>" in text
        if "?" in line:
            assert "&ok=keep" in text
        if line.startswith('"token"'):
            assert json.loads("{" + text + "}") == {"token": "<redacted>"}


def test_redacts_active_admin_token_even_without_a_field_name(export_client):
    client, _, directory, _ = export_client
    (directory / "app.log").write_text("standalone " + TOKEN, encoding="utf-8")
    with _export(client) as archive:
        text = archive.read("logs/app.log").decode("utf-8")
        assert TOKEN not in text and "<redacted>" in text


def test_redacts_individual_values_from_configured_cookie_strings(export_client):
    client, config, directory, _ = export_client
    config["input"] = {"cookies": "SID=first-cookie-value; session=second-cookie-value",
                       "cookies_by_site": {"youtube": "LOGIN=site-cookie-value; other=other-value"}}
    (directory / "app.log").write_text(
        "first-cookie-value\nSID=first-cookie-value\nsecond-cookie-value\nsite-cookie-value\nother-value",
        encoding="utf-8",
    )
    with _export(client) as archive:
        text = archive.read("logs/app.log").decode("utf-8")
        for value in ("first-cookie-value", "second-cookie-value", "site-cookie-value", "other-value"):
            assert value not in text
        assert "<redacted>" in text


def test_multi_gigabyte_log_reads_only_bounded_tail(export_client, monkeypatch):
    client, _, directory, _ = export_client
    monkeypatch.setattr(runtime, "LOG_EXPORT_MAX_BYTES", 3200)
    path = directory / "big.log"
    path.write_bytes(b"placeholder")
    logical_size = 8 * 1024 * 1024 * 1024
    reads = []
    seeks = []
    original_open = type(path).open

    class LargeLog:
        # Model a sparse multi-GB log without allocating disk space or RAM.
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def seek(self, offset, whence=io.SEEK_SET):
            seeks.append((offset, whence))
            self.position = logical_size if whence == io.SEEK_END else offset

        def tell(self):
            return self.position

        def read(self, size=-1):
            assert 0 < size <= runtime.LOG_EXPORT_MAX_BYTES
            assert self.position == logical_size - size
            reads.append(size)
            return b"half-token-" + b"X" * (size - 17) + b"\nTAIL\n"

    def open_log(candidate, mode="r", *args, **kwargs):
        if candidate == path:
            assert mode == "rb"
            return LargeLog()
        return original_open(candidate, mode, *args, **kwargs)

    monkeypatch.setattr(type(path), "open", open_log)
    with _export(client) as archive:
        assert archive.read("logs/big.log") == b"TAIL\n"
        assert sum(info.file_size for info in archive.infolist()) <= 3200
        assert "截斷：big.log" in archive.read("export-notes.txt").decode("utf-8")
    assert len(reads) == 1
    assert seeks == [(0, io.SEEK_END), (logical_size - reads[0], io.SEEK_SET)]


@pytest.mark.parametrize("name", ["api_key", "openai_api_key", "google_api_key"])
def test_redacts_each_configured_key_pool_member(export_client, name):
    client, config, directory, _ = export_client
    config["provider"] = {name: " sk-first-secret, sk-second-secret ,abc"}
    # Pool formatting differs from config, and keys also appear without a field.
    (directory / "app.log").write_text(
        "api_key=sk-first-secret,sk-second-secret\n"
        "standalone sk-first-secret\nstandalone sk-second-secret\nabc",
        encoding="utf-8",
    )
    with _export(client) as archive:
        text = archive.read("logs/app.log").decode("utf-8")
        assert "sk-first-secret" not in text
        assert "sk-second-secret" not in text
        assert "<redacted>" in text
        assert "abc" in text  # Individual configured values shorter than four stay ignored.


@pytest.mark.parametrize("line", [
    "api_key=old-first-secret,old-second-secret",
    "api_key=old-first-secret, old-second-secret",
    "api_key: old-first-secret , old-second-secret",
])
def test_redacts_entire_old_key_pool_without_config(export_client, line):
    client, _, directory, _ = export_client
    (directory / "backend.log.1").write_text(line, encoding="utf-8")
    with _export(client) as archive:
        text = archive.read("logs/backend.log.1").decode("utf-8")
        assert "old-first-secret" not in text
        assert "old-second-secret" not in text
        assert "<redacted>" in text


@pytest.mark.parametrize("line", [
    "{'Cookie': b'session=old-secret; other=second-secret'}",
    '{"Cookie": b"session=old-secret; other=second-secret"}',
    "{'Set-Cookie': r'session=old-secret; other=second-secret'}",
    "{'Authorization': b'Bearer old-secret'}",
    '{"Authorization": r"Basic old-secret"}',
    r'{\"Authorization\": \"Bearer old-secret\"}',
    r"{\'Cookie\': b\'session=old-secret; other=second-secret\'}",
    r'{\"Cookie\": r\"session=old-secret; other=second-secret\"}',
    r'{\"api_key\": b\"old-secret,second-secret\"}',
    "{'token': r'old-secret'}",
    json.dumps(json.dumps({"Authorization": "Bearer old-secret"})),
    json.dumps(json.dumps(json.dumps({"Cookie": "session=old-secret; other=second-secret"}))),
])
def test_redacts_serialized_headers_and_fields_completely(export_client, line):
    client, _, directory, _ = export_client
    (directory / "backend.log.1").write_text("headers=" + line, encoding="utf-8")
    with _export(client) as archive:
        text = archive.read("logs/backend.log.1").decode("utf-8")
        assert "old-secret" not in text
        assert "second-secret" not in text
        assert "<redacted>" in text
