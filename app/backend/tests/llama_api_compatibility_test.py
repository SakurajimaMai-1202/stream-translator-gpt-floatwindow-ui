from types import SimpleNamespace

from backend.api import llama


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

    assert llama._flash_attn_args("new-llama-server.exe") == ["--flash-attn", "on"]


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

    assert llama._flash_attn_args("old-llama-server.exe") == ["--flash-attn"]
