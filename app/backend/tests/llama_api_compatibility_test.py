from types import SimpleNamespace
from fastapi import Request

from backend.api import llama
from backend.api import config as config_api


def test_failed_server_reports_missing_tensor_instead_of_exit_summary(monkeypatch, tmp_path):
    import asyncio
    import io
    import threading

    model = tmp_path / "Index-Translate-9B.gguf"
    runtime = tmp_path / "llama-server.exe"
    model.write_bytes(b"GGUF")
    runtime.write_bytes(b"runtime")
    root_cause = "llama_model_load: error loading model: missing tensor 'blk.32.ssm_conv1d.weight'"
    process = SimpleNamespace(
        pid=123,
        stdout=io.StringIO(""),
        stderr=io.StringIO("\n".join([
            root_cause,
            "llama_model_load_from_file_impl: failed to load model",
            f"common_init_from_params: failed to load model '{model}'",
            "main: exiting due to model loading error",
        ]) + "\n"),
        wait=lambda: 1,
    )
    pending = []
    original_thread = threading.Thread

    class DeferredThread:
        def __new__(cls, target, args=(), **kwargs):
            if target.__name__ not in {"log_output", "monitor_process"}:
                return original_thread(target=target, args=args, **kwargs)
            return super().__new__(cls)

        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args

        def start(self):
            pending.append(lambda: self.target(*self.args))

    monkeypatch.setattr(llama, "llama_state", llama.LlamaState())
    monkeypatch.setattr(llama, "popen_external", lambda *args, **kwargs: process)
    monkeypatch.setattr(llama, "_flash_attn_args", lambda *args: [])
    monkeypatch.setattr(threading, "Thread", DeferredThread)
    monkeypatch.setattr(llama, "configure_dedicated_file_logger", lambda *args: llama.logger)

    asyncio.run(llama.start_server(
        llama.ServerConfig(model_path=str(model), server_exe=str(runtime)),
        llama.BackgroundTasks(),
        Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
    ))
    for run in pending:
        run()

    assert llama.llama_state.last_error == root_cause
    assert llama.llama_state.is_running is False
    assert llama.llama_state.server_process is None


def test_server_error_can_replace_generic_exit_with_delayed_root_cause():
    root_cause = "llama_model_load: error loading model: missing tensor 'blk.32.ssm_conv1d.weight'"
    assert llama._select_server_error("llama-server exited with code 1", root_cause) == root_cause
    assert llama._select_server_error(root_cause, "load_tensors: loading model tensors...") == root_cause


def test_relative_model_directory_is_resolved_from_portable_app_root(monkeypatch, tmp_path):
    app_root = tmp_path / "portable"
    model_dir = app_root / "models"
    model_dir.mkdir(parents=True)
    model_file = model_dir / "Hy-MT2.gguf"
    model_file.write_bytes(b"gguf")
    monkeypatch.setattr(llama, "get_app_root", lambda: app_root)

    import asyncio
    result = asyncio.run(llama.list_models("./models"))

    assert [model.name for model in result] == ["Hy-MT2.gguf"]
    assert result[0].path == str(model_file.absolute())


def test_configured_llama_runtime_has_priority_and_does_not_fallback(monkeypatch, tmp_path):
    configured = tmp_path / "custom" / "llama-server.exe"
    configured.parent.mkdir()
    configured.write_bytes(b"runtime")

    class ConfigManager:
        def get_config(self):
            return {"llama": {"server_exe": str(configured)}}

    monkeypatch.setattr(config_api, "get_config_manager", lambda: ConfigManager())
    assert llama._find_llama_server() == configured.resolve()

    configured.unlink()
    assert llama._find_llama_server() is None


def test_relative_custom_runtime_is_resolved_from_app_root(monkeypatch, tmp_path):
    monkeypatch.setattr(llama, "get_app_root", lambda: tmp_path)
    expected = tmp_path / "tools" / "llama-server.exe"
    assert llama._resolve_user_path("tools/llama-server.exe") == expected.resolve()


def test_custom_runtime_directory_resolves_to_server(monkeypatch, tmp_path):
    import asyncio

    runtime_dir = tmp_path / "custom"
    runtime_dir.mkdir()
    executable = runtime_dir / "llama-server.exe"
    executable.write_bytes(b"runtime")

    class ConfigManager:
        def get_config(self):
            return {"llama": {"server_exe": str(runtime_dir)}}

    monkeypatch.setattr(config_api, "get_config_manager", lambda: ConfigManager())
    monkeypatch.setattr(
        llama, "run_external",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="version: test\n", stderr=""),
    )
    assert llama._find_llama_server() == executable.resolve()
    result = asyncio.run(llama.validate_runtime_path(
        llama.RuntimePathRequest(server_exe=str(runtime_dir)),
        Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
    ))
    assert result["path"] == str(executable.resolve())


def test_custom_runtime_directory_without_server_does_not_fallback(monkeypatch, tmp_path):
    import asyncio
    import pytest

    runtime_dir = tmp_path / "empty"
    runtime_dir.mkdir()

    class ConfigManager:
        def get_config(self):
            return {"llama": {"server_exe": str(runtime_dir)}}

    monkeypatch.setattr(config_api, "get_config_manager", lambda: ConfigManager())
    assert llama._find_llama_server() is None
    with pytest.raises(llama.HTTPException, match="llama-server.exe"):
        asyncio.run(llama.validate_runtime_path(
            llama.RuntimePathRequest(server_exe=str(runtime_dir)),
            Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []}),
        ))


def test_validate_model_path_checks_gguf_header(tmp_path):
    import asyncio
    model = tmp_path / "translation.gguf"
    model.write_bytes(b"GGUF" + b"\0" * 16)
    result = asyncio.run(llama.validate_model_path(llama.ModelPathRequest(model_path=str(model))))
    assert result["path"] == str(model.resolve())


def test_validate_model_path_rejects_renamed_file(tmp_path):
    import asyncio
    import pytest
    model = tmp_path / "translation.gguf"
    model.write_bytes(b"ZIP!")
    with pytest.raises(llama.HTTPException, match="GGUF"):
        asyncio.run(llama.validate_model_path(llama.ModelPathRequest(model_path=str(model))))


def test_resource_status_reuses_short_lived_cache(monkeypatch):
    calls = 0

    def fake_run(*args, **kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(
            returncode=0,
            stdout="Test GPU, 100, 1000, 25\n",
            stderr="",
        )

    monkeypatch.setattr(llama.subprocess, "run", fake_run)
    monkeypatch.setattr(llama, "_resource_status_cache", {})
    monkeypatch.setattr(llama, "_resource_status_cache_at", 0.0)

    first = llama._collect_resource_status()
    second = llama._collect_resource_status()

    assert calls == 1
    assert first == second
    assert second["gpu_name"] == "Test GPU"


def test_flash_attention_uses_explicit_value_for_new_runtime(monkeypatch):
    llama._flash_attn_args.cache_clear()
    monkeypatch.setattr(
        llama,
        "run_external",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="--flash-attn [on|off|auto] set Flash Attention use",
            stderr="",
        ),
    )

    assert llama._flash_attn_args("new-llama-server.exe", "auto") == ["--flash-attn", "auto"]


def test_flash_attention_uses_boolean_switch_for_old_runtime(monkeypatch):
    llama._flash_attn_args.cache_clear()
    monkeypatch.setattr(
        llama,
        "run_external",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="--flash-attn enable Flash Attention",
            stderr="",
        ),
    )

    assert llama._flash_attn_args("old-llama-server.exe", "on") == ["--flash-attn"]
    assert llama._flash_attn_args("old-llama-server.exe", "auto") == []


def test_no_mmap_uses_load_mode_none_for_new_runtime(monkeypatch):
    llama._no_mmap_args.cache_clear()
    monkeypatch.setattr(
        llama,
        "run_external",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="--load-mode MODE model loading mode",
            stderr="",
        ),
    )

    assert llama._no_mmap_args("new-llama-server.exe") == ["--load-mode", "none"]


def test_no_mmap_uses_legacy_switch_for_old_runtime(monkeypatch):
    llama._no_mmap_args.cache_clear()
    monkeypatch.setattr(
        llama,
        "run_external",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="--mmap, --no-mmap whether to memory-map model",
            stderr="",
        ),
    )

    assert llama._no_mmap_args("old-llama-server.exe") == ["--no-mmap"]


def test_hymt_models_force_flash_attention_and_mmap_off():
    assert llama._is_hymt_model("Hy-MT2-7B.i1-Q6_K.gguf") is True
    assert llama._is_hymt_model("hy_mt-translation.gguf") is True
    assert llama._effective_memory_options("Hy-MT2-7B.gguf", "auto", False) == ("off", True)


def test_other_models_keep_requested_memory_options():
    assert llama._is_hymt_model("gemma-4-e2b.gguf") is False
    assert llama._effective_memory_options("gemma-4-e2b.gguf", "auto", False) == ("auto", False)


def test_translation_uses_saved_model_sampling_parameters(monkeypatch):
    captured = {}

    class ConfigManager:
        def get_config(self):
            return {"llama": {"temp": 0.7, "top_p": 0.6, "top_k": 20, "repeat_penalty": 1.05, "n_predict": 768}}

    async def fake_inference(request):
        captured.update(request.model_dump())
        return {"text": "譯文", "model": "HY-MT"}

    monkeypatch.setattr(config_api, "get_config_manager", lambda: ConfigManager())
    monkeypatch.setattr(llama, "inference", fake_inference)
    monkeypatch.setattr(llama.llama_state, "is_running", True)

    import asyncio
    result = asyncio.run(llama.translate_with_llama(llama.TranslateRequest(text="hello")))

    assert result["translated"] == "譯文"
    assert captured["temperature"] == 0.7
    assert captured["top_p"] == 0.6
    assert captured["top_k"] == 20
    assert captured["repeat_penalty"] == 1.05
    assert captured["max_tokens"] == 768


def _fake_server_launch(monkeypatch, tmp_path):
    import asyncio
    import io
    import threading

    model = tmp_path / "model.gguf"
    runtime = tmp_path / "llama-server.exe"
    model.write_bytes(b"GGUF")
    runtime.write_bytes(b"runtime")
    processes = []
    pending = []
    original_thread = threading.Thread

    class DeferredThread:
        def __new__(cls, target, args=(), **kwargs):
            if target.__name__ not in {"log_output", "monitor_process"}:
                return original_thread(target=target, args=args, **kwargs)
            return super().__new__(cls)

        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args

        def start(self):
            pending.append(self.target.__name__)

    def fake_popen(*args, **kwargs):
        events = []
        process = SimpleNamespace(
            pid=123 + len(processes), stdout=io.StringIO(""), stderr=io.StringIO(""),
            kill=lambda: events.append("kill"),
            wait=lambda timeout=None: events.append(("wait", timeout)) or 0,
            events=events,
        )
        processes.append(process)
        return process

    monkeypatch.setattr(llama, "llama_state", llama.LlamaState())
    monkeypatch.setattr(llama, "_server_start_lock", asyncio.Lock())
    monkeypatch.setattr(llama, "_find_llama_server", lambda: runtime)
    monkeypatch.setattr(llama, "popen_external", fake_popen)
    monkeypatch.setattr(llama, "supports_device_selection", lambda *args: False)
    monkeypatch.setattr(llama, "_flash_attn_args", lambda *args: [])
    monkeypatch.setattr(llama, "configure_dedicated_file_logger", lambda *args: llama.logger)
    monkeypatch.setattr(threading, "Thread", DeferredThread)
    config = llama.ServerConfig(model_path=str(model))
    request = Request({"type": "http", "client": ("127.0.0.1", 12345), "headers": []})
    return config, request, processes, DeferredThread


def test_concurrent_server_starts_spawn_once_and_stop_rejects_starting(monkeypatch, tmp_path):
    import asyncio
    import pytest

    config, request, processes, _ = _fake_server_launch(monkeypatch, tmp_path)
    original_to_thread = asyncio.to_thread

    async def scenario():
        resolving = asyncio.Event()
        release = asyncio.Event()

        async def slow_to_thread(func, *args, **kwargs):
            if func is llama.supports_device_selection:
                resolving.set()
                await release.wait()
                return False
            return await original_to_thread(func, *args, **kwargs)

        monkeypatch.setattr(asyncio, "to_thread", slow_to_thread)

        async def second_start():
            await resolving.wait()
            try:
                with pytest.raises(llama.HTTPException) as stopped:
                    await llama.stop_server()
                assert stopped.value.status_code == 409
                assert "啟動中" in stopped.value.detail
                assert processes == []
                return await llama.start_server(config, llama.BackgroundTasks(), request)
            finally:
                release.set()

        results = await asyncio.gather(
            llama.start_server(config, llama.BackgroundTasks(), request),
            second_start(), return_exceptions=True,
        )
        assert results[0]["status"] == "started"
        assert isinstance(results[1], llama.HTTPException)
        assert results[1].status_code == 409
        assert "啟動中" in results[1].detail
        assert len(processes) == 1
        assert llama.llama_state.server_process is processes[0]
        assert not llama._server_start_lock.locked()
        with pytest.raises(llama.HTTPException) as running:
            await llama.start_server(config, llama.BackgroundTasks(), request)
        assert "執行中" in running.value.detail
        assert len(processes) == 1

    asyncio.run(scenario())


def test_failed_start_kills_waits_and_allows_retry(monkeypatch, tmp_path):
    import asyncio
    import pytest

    config, request, processes, thread = _fake_server_launch(monkeypatch, tmp_path)
    original_start = thread.start

    def fail_monitor(self):
        if self.target.__name__ == "monitor_process":
            raise RuntimeError("monitor thread failed")
        original_start(self)

    monkeypatch.setattr(thread, "start", fail_monitor)

    async def scenario():
        with pytest.raises(llama.HTTPException) as failed:
            await llama.start_server(config, llama.BackgroundTasks(), request)
        assert failed.value.status_code == 500
        assert processes[0].events == ["kill", ("wait", 5)]
        assert llama.llama_state.server_process is None
        assert not llama.llama_state.is_running
        assert not llama.llama_state.is_ready
        assert not llama._server_start_lock.locked()
        monkeypatch.setattr(thread, "start", original_start)
        result = await llama.start_server(config, llama.BackgroundTasks(), request)
        assert result["status"] == "started"
        assert len(processes) == 2
        assert llama.llama_state.server_process is processes[1]

    asyncio.run(scenario())


def test_start_validation_error_releases_lock(monkeypatch, tmp_path):
    import asyncio
    import pytest

    config, request, processes, _ = _fake_server_launch(monkeypatch, tmp_path)

    async def scenario():
        with pytest.raises(llama.HTTPException) as failed:
            await llama.start_server(llama.ServerConfig(), llama.BackgroundTasks(), request)
        assert failed.value.status_code == 400
        assert not llama._server_start_lock.locked()
        assert processes == []
        assert (await llama.start_server(config, llama.BackgroundTasks(), request))["status"] == "started"

    asyncio.run(scenario())


def test_failed_start_does_not_clear_newer_process_state(monkeypatch, tmp_path):
    import asyncio
    import pytest

    config, request, processes, thread = _fake_server_launch(monkeypatch, tmp_path)
    newer = object()

    def fail_monitor(self):
        if self.target.__name__ == "monitor_process":
            llama.llama_state.server_process = newer
            llama.llama_state.is_ready = True
            raise RuntimeError("monitor thread failed")

    monkeypatch.setattr(thread, "start", fail_monitor)
    with pytest.raises(llama.HTTPException):
        asyncio.run(llama.start_server(config, llama.BackgroundTasks(), request))
    assert processes[0].events == ["kill", ("wait", 5)]
    assert llama.llama_state.server_process is newer
    assert llama.llama_state.is_running
    assert llama.llama_state.is_ready
    assert not llama._server_start_lock.locked()


def test_stop_adopted_external_server_preserves_state(monkeypatch):
    import asyncio
    import pytest

    state = llama.LlamaState()
    state.is_running = True
    state.is_ready = True
    state.server_url = "http://127.0.0.1:8081"
    state.current_model = "external.gguf"
    state.gpu_selection = {"mode": "external"}
    before = vars(state).copy()
    monkeypatch.setattr(llama, "llama_state", state)
    monkeypatch.setattr(llama, "_server_start_lock", asyncio.Lock())

    with pytest.raises(llama.HTTPException) as stopped:
        asyncio.run(llama.stop_server())
    assert stopped.value.status_code == 409
    assert "並非由本應用程式啟動" in stopped.value.detail
    assert "手動關閉" in stopped.value.detail
    assert vars(state) == before
