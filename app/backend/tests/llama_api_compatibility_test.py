from types import SimpleNamespace

from backend.api import llama
from backend.api import config as config_api


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
        llama.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="--flash-attn [on|off|auto] set Flash Attention use",
            stderr="",
        ),
    )

    assert llama._flash_attn_args("new-llama-server.exe", "auto") == ["--flash-attn", "auto"]


def test_flash_attention_uses_boolean_switch_for_old_runtime(monkeypatch):
    llama._flash_attn_args.cache_clear()
    monkeypatch.setattr(
        llama.subprocess,
        "run",
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
        llama.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            stdout="--load-mode MODE model loading mode",
            stderr="",
        ),
    )

    assert llama._no_mmap_args("new-llama-server.exe") == ["--load-mode", "none"]


def test_no_mmap_uses_legacy_switch_for_old_runtime(monkeypatch):
    llama._no_mmap_args.cache_clear()
    monkeypatch.setattr(
        llama.subprocess,
        "run",
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
