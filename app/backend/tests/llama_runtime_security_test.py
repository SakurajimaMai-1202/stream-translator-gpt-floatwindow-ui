import asyncio
from types import SimpleNamespace

import pytest
from fastapi import Request, HTTPException

from backend.api import llama


def make_request(host="127.0.0.1", headers=()):
    return Request({"type": "http", "client": (host, 12345), "headers": headers})


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    executable = tmp_path / "custom" / "llama-server.exe"
    executable.parent.mkdir()
    executable.write_bytes(b"runtime")
    monkeypatch.setattr(llama, "llama_root", lambda: tmp_path / "managed")
    monkeypatch.setattr(llama, "_configured_llama_server", lambda: (None, False))
    return executable


def test_managed_runtime_allowed(monkeypatch, runtime):
    monkeypatch.setattr(llama, "llama_root", lambda: runtime.parent)
    llama._guard_custom_runtime(runtime, make_request("192.0.2.1"))


def test_configured_runtime_allowed(monkeypatch, runtime):
    monkeypatch.setattr(llama, "_configured_llama_server", lambda: (runtime, True))
    llama._guard_custom_runtime(runtime, make_request("192.0.2.1"))


@pytest.mark.parametrize("host", ["127.0.0.1", "::1"])
def test_direct_loopback_runtime_allowed(runtime, host):
    llama._guard_custom_runtime(runtime, make_request(host))


@pytest.mark.parametrize("endpoint", ["start", "devices", "validate"])
@pytest.mark.parametrize("host,headers", [
    ("192.0.2.1", ()),
    ("127.0.0.1", ((b"x-forwarded-for", b"192.0.2.1"),)),
    ("127.0.0.1", ((b"x-real-ip", b"192.0.2.1"),)),
    ("::1", ((b"forwarded", b"for=192.0.2.1"),)),
    ("127.0.0.1", ((b"forwarded", b""),)),
])
def test_untrusted_custom_runtime_rejected_before_execution(monkeypatch, runtime, endpoint, host, headers):
    request = make_request(host, headers)
    monkeypatch.setattr(llama, "llama_state", llama.LlamaState())

    def unexpected_execution(*args, **kwargs):
        pytest.fail("未授權的 Runtime 不應執行")

    for name in ("run_external", "popen_external", "enumerate_devices", "supports_device_selection"):
        monkeypatch.setattr(llama, name, unexpected_execution)
    if endpoint == "start":
        model = runtime.parent / "model.gguf"
        model.write_bytes(b"GGUF")
        call = llama.start_server(
            llama.ServerConfig(model_path=str(model), server_exe=str(runtime)),
            llama.BackgroundTasks(), request,
        )
    elif endpoint == "devices":
        call = llama.get_runtime_devices(request, server_exe=str(runtime))
    else:
        call = llama.validate_runtime_path(llama.RuntimePathRequest(server_exe=str(runtime)), request)
    with pytest.raises(HTTPException) as error:
        asyncio.run(call)
    assert error.value.status_code == 403


@pytest.mark.parametrize("configured", [False, True])
def test_non_llama_filename_rejected_even_locally(monkeypatch, runtime, configured):
    executable = runtime.with_name("other.exe")
    executable.write_bytes(b"other")
    if configured:
        monkeypatch.setattr(llama, "_configured_llama_server", lambda: (executable, True))
    with pytest.raises(HTTPException) as error:
        llama._guard_custom_runtime(executable, make_request())
    assert error.value.status_code == 403


def test_directory_path_still_validates_from_direct_loopback(monkeypatch, runtime):
    monkeypatch.setattr(llama, "run_external", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout="version: test", stderr="",
    ))
    result = asyncio.run(llama.validate_runtime_path(
        llama.RuntimePathRequest(server_exe=str(runtime.parent)), make_request(),
    ))
    assert result["path"] == str(runtime.resolve())
