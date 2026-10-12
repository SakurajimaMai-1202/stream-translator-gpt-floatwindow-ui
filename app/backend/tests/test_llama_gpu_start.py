"""Exercise command construction without launching a model or worker threads."""
import asyncio
import io
from types import SimpleNamespace

import pytest
from fastapi import Request

from backend.api import llama


@pytest.fixture
def launch(monkeypatch, tmp_path):
    model = tmp_path / "test.gguf"
    runtime = tmp_path / "llama-server.exe"
    model.touch()
    runtime.touch()
    captured = {}
    def popen(cmd, **kwargs):
        captured.update(cmd=cmd, kwargs=kwargs)
        return SimpleNamespace(pid=12, stdout=io.StringIO(), stderr=io.StringIO())
    import threading
    original_thread = threading.Thread
    def thread_factory(*args, **kwargs):
        target = kwargs.get("target")
        if target and target.__name__ in {"log_output", "monitor_process"}:
            return SimpleNamespace(start=lambda: None)
        return original_thread(*args, **kwargs)
    monkeypatch.setattr(threading, "Thread", thread_factory)
    monkeypatch.setattr(llama, "llama_state", llama.LlamaState())
    monkeypatch.setattr(llama, "_server_start_lock", asyncio.Lock())
    monkeypatch.setattr(llama, "popen_external", popen)
    monkeypatch.setattr(llama, "_flash_attn_args", lambda *args: [])
    monkeypatch.setattr(llama, "supports_device_selection", lambda *args: True)
    monkeypatch.setattr(llama, "gpu_logging_args", lambda *args: ["--verbosity", "4"])
    monkeypatch.setattr(llama, "configure_dedicated_file_logger", lambda *args: llama.logger)
    devices = [dict(id="Vulkan0", name="Intel Arc Graphics", memory_mb=15000, is_integrated=True, eligible=False),
               dict(id="Vulkan1", name="AMD Radeon RX 7600", memory_mb=8192, is_integrated=False, eligible=True)]
    monkeypatch.setattr(llama, "enumerate_devices", lambda *args: dict(devices=devices, error=None))
    def start(**kwargs):
        config = llama.ServerConfig(model_path=str(model), server_exe=str(runtime), **kwargs)
        request = Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []})
        return asyncio.run(llama.start_server(config, llama.BackgroundTasks(), request))
    return start, captured


def test_auto_discrete_single_device_and_sanitized_env(launch, monkeypatch):
    monkeypatch.setenv("LLAMA_ARG_DEVICE", "Vulkan0")
    monkeypatch.setenv("LLAMA_ARG_TENSOR_SPLIT", "1,1")
    start, captured = launch
    start(n_gpu_layers=99)
    cmd = captured["cmd"]
    assert cmd[cmd.index("--device") + 1] == "Vulkan1"
    assert cmd[cmd.index("--split-mode") + 1] == "none"
    assert cmd[cmd.index("--verbosity") + 1] == "4"
    assert "LLAMA_ARG_DEVICE" not in captured["kwargs"]["env"]
    assert "LLAMA_ARG_TENSOR_SPLIT" not in captured["kwargs"]["env"]
    assert not llama.llama_state.gpu_selection["confirmed"]


def test_manual_name_change_rejected_before_launch(launch):
    start, captured = launch
    with pytest.raises(llama.HTTPException) as error:
        start(n_gpu_layers=99, gpu_device="Vulkan1", gpu_device_name="Intel Arc A770")
    assert error.value.status_code == 400
    assert not captured


def test_missing_gpu_and_integrated_rejected(launch):
    start, captured = launch
    for device in ("Vulkan9", "Vulkan0"):
        with pytest.raises(llama.HTTPException):
            start(n_gpu_layers=99, gpu_device=device)
    assert not captured


def test_cpu_disables_devices_and_legacy_remains_launchable(launch, monkeypatch):
    start, captured = launch
    start(n_gpu_layers=0)
    cmd = captured["cmd"]
    assert cmd[cmd.index("--device") + 1] == "none"
    llama.llama_state = llama.LlamaState()
    monkeypatch.setattr(llama, "supports_device_selection", lambda *args: False)
    start(n_gpu_layers=0)
    assert "--device" not in captured["cmd"]
    assert llama.llama_state.gpu_selection["mode"] == "unknown"
