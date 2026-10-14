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
    monkeypatch.setattr(llama, "assign_process", lambda process: captured.setdefault("assigned", process))
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
    assert captured["assigned"].pid == 12


def test_server_launch_disables_implicit_vulkan_layers(launch, monkeypatch):
    monkeypatch.delenv("VK_LOADER_LAYERS_DISABLE", raising=False)
    start, captured = launch
    start(n_gpu_layers=99)
    assert captured["kwargs"]["env"]["VK_LOADER_LAYERS_DISABLE"] == "~implicit~"


def test_index_translate_launch_disables_thinking(launch, monkeypatch):
    flags = ["--chat-template-kwargs", '{"enable_thinking": false}']
    monkeypatch.setattr(llama, "_disable_thinking_args", lambda *args: flags)
    start, captured = launch
    start(n_gpu_layers=99)
    assert "--chat-template-kwargs" not in captured["cmd"]  # test.gguf is not Index-Translate

    monkeypatch.setattr(llama, "_is_index_translate_model", lambda *args: True)
    monkeypatch.setattr(llama, "llama_state", llama.LlamaState())
    start(n_gpu_layers=99)
    cmd = captured["cmd"]
    assert cmd[cmd.index("--chat-template-kwargs") + 1] == '{"enable_thinking": false}'


def test_user_vulkan_layer_setting_is_kept(launch, monkeypatch):
    monkeypatch.setenv("VK_LOADER_LAYERS_DISABLE", "VK_LAYER_VALVE_steam_overlay")
    start, captured = launch
    start(n_gpu_layers=99)
    assert captured["kwargs"]["env"]["VK_LOADER_LAYERS_DISABLE"] == "VK_LAYER_VALVE_steam_overlay"


def test_device_and_version_probes_disable_implicit_vulkan_layers(monkeypatch, tmp_path):
    from backend.core import llama_devices, llama_runtime_installer
    monkeypatch.delenv("VK_LOADER_LAYERS_DISABLE", raising=False)
    envs = []
    def run(args, **kwargs):
        envs.append(kwargs.get("env") or {})
        return SimpleNamespace(returncode=0, stdout="version: 1 (abc)", stderr="")
    monkeypatch.setattr(llama_devices, "run_external", run)
    monkeypatch.setattr(llama_runtime_installer, "run_external", run)
    monkeypatch.setattr(llama_devices, "detect_windows_dxgi_adapters", lambda: [])
    llama_devices.enumerate_devices(str(tmp_path / "llama-server.exe"))
    server = tmp_path / "llama-server.exe"
    server.touch()
    llama_runtime_installer.LlamaRuntimeInstaller._validate_runtime(tmp_path)
    assert len(envs) == 2
    assert all(env.get("VK_LOADER_LAYERS_DISABLE") == "~implicit~" for env in envs)


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
