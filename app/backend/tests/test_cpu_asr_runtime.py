import asyncio
from pathlib import Path
from unittest.mock import Mock

import pytest

from backend.core import cpu_asr_runtime as runtime
from backend.core import translator
from backend.core import model_download_manager as downloads


def registry(root, text):
    path = root / "Lib/site-packages/stream_translator_gpt/sherpa_onnx_models.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_engine_fingerprint_contents_and_cache(monkeypatch, tmp_path):
    package = tmp_path / 'engine'
    assert runtime.engine_fingerprint(package) is None
    package.mkdir()
    source = package / 'main.py'
    source.write_bytes(b'first')
    initial = runtime.engine_fingerprint(package)
    (package / '__pycache__').mkdir()
    (package / '__pycache__/ignored.txt').write_bytes(b'ignored')
    (package / 'ignored.pyc').write_bytes(b'ignored')
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_bytes', Mock(side_effect=AssertionError('cached digest')))
        assert runtime.engine_fingerprint(package) == initial
    source.write_bytes(b'changed contents')
    changed = runtime.engine_fingerprint(package)
    assert changed != initial
    source.rename(package / 'renamed.py')
    # A fresh directory with identical bytes but different paths hashes differently.
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'main.py').write_bytes(b'changed contents')
    runtime._engine_fingerprints.clear()
    assert runtime.engine_fingerprint(package) != runtime.engine_fingerprint(other)


@pytest.mark.parametrize('frozen,compute,profile,folder,main,sidecar,mismatch', [
    (True, 'cpu', 'cuda', '_runtime_cpu_asr', True, 'old', True),
    (True, 'cpu', 'rocm', '_runtime_cpu_asr', True, None, True),
    (True, 'cpu', 'cuda', '_runtime_cpu_asr', True, 'current', False),
    (False, 'cpu', 'cuda', '_runtime_cpu_asr', True, 'old', False),
    (True, 'cuda', 'cuda', '_runtime_cpu_asr', True, 'old', False),
    (True, 'cpu', 'cpu', '_runtime_cpu_asr', True, 'old', False),
    (True, 'cpu', 'cuda', 'fallback', True, 'old', False),
    (True, 'cpu', 'cuda', '_runtime_cpu_asr', False, 'old', False),
])
def test_sidecar_engine_mismatch(monkeypatch, tmp_path, frozen, compute, profile, folder,
                                main, sidecar, mismatch):
    monkeypatch.setattr(runtime.sys, 'frozen', frozen, raising=False)
    monkeypatch.setattr(runtime.sys, 'executable', str(tmp_path / 'app.exe'))
    monkeypatch.setattr(runtime, 'resolve_profile_python', lambda *args: str(tmp_path / folder / 'python.exe'))
    if main:
        registry(tmp_path / '_runtime', 'current')
    if sidecar:
        registry(tmp_path / '_runtime_cpu_asr', sidecar)
    message = runtime.sidecar_engine_mismatch_message(profile, compute)
    assert message == ('CPU ASR Runtime 內的翻譯引擎與主程式版本不一致，請到「ASR 模型管理」重新安裝 CPU ASR Runtime 後再試。' if mismatch else None)


def test_build_command_blocks_engine_mismatch_before_validation(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime.sys, 'frozen', True, raising=False)
    monkeypatch.setattr(runtime.sys, 'executable', str(tmp_path / 'app.exe'))
    python = tmp_path / '_runtime_cpu_asr/python.exe'
    python.parent.mkdir()
    python.touch()
    registry(tmp_path / '_runtime', 'current')
    registry(python.parent, 'old')
    monkeypatch.setattr(translator, '_resolve_profile_python', lambda *args: str(python))
    validate = Mock(side_effect=AssertionError('must not spawn'))
    monkeypatch.setattr(translator, '_validate_cpu_asr_runtime', validate)
    context = translator.TranslationContext({'runtime_profile': 'cuda', 'asr_compute_backend': 'cpu'}, 'test')
    with pytest.raises(RuntimeError) as error:
        context._build_command()
    assert str(error.value) == runtime.sidecar_engine_mismatch_message('cuda', 'cpu')
    validate.assert_not_called()


def test_runtime_contains_model(tmp_path):
    assert not runtime.runtime_contains_model(tmp_path, runtime.HAAS_MODEL_ID)
    registry(tmp_path, "other model")
    assert not runtime.runtime_contains_model(tmp_path, runtime.HAAS_MODEL_ID)
    registry(tmp_path, runtime.HAAS_MODEL_ID)
    assert runtime.runtime_contains_model(tmp_path, runtime.HAAS_MODEL_ID)


@pytest.mark.parametrize("profile,message", [
    ("cuda", "目前安裝的 CPU ASR Runtime 版本過舊，不支援 Haas。請到「ASR 模型管理」重新安裝 CPU ASR Runtime 後再試。"),
    ("rocm", "目前安裝的 CPU ASR Runtime 版本過舊，不支援 Haas。請到「ASR 模型管理」重新安裝 CPU ASR Runtime 後再試。"),
    ("cpu", "目前的 CPU 執行環境版本過舊，不支援 Haas。請下載完整安裝包更新後再試。"),
])
def test_frozen_haas_start_refused_before_probe(monkeypatch, tmp_path, profile, message):
    monkeypatch.setattr(translator.sys, "frozen", True, raising=False)
    monkeypatch.setattr(translator, "_resolve_profile_python", lambda *a: str(tmp_path / "python.exe"))
    monkeypatch.setattr(runtime, "resolve_profile_python", lambda *a: str(tmp_path / "python.exe"))
    probe = Mock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(translator, "_validate_cpu_asr_runtime", probe)
    context = translator.TranslationContext({"asr_compute_backend": "cpu", "runtime_profile": profile,
        "use_nemo_asr": True, "nemo_asr_model": runtime.HAAS_MODEL_ID, "model": "unrelated"}, "test")
    with pytest.raises(RuntimeError) as error:
        context._build_command()
    assert str(error.value) == message
    probe.assert_not_called()


@pytest.mark.parametrize("frozen,current,model,use_nemo", [
    (True, True, runtime.HAAS_MODEL_ID, True),
    (False, False, runtime.HAAS_MODEL_ID, True),
    (True, False, "nvidia/parakeet-tdt-0.6b-v3", True),
    (True, False, runtime.HAAS_MODEL_ID, False),
])
def test_start_compatibility_exemptions(monkeypatch, tmp_path, frozen, current, model, use_nemo):
    monkeypatch.setattr(translator.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(translator, "_resolve_profile_python", lambda *a: str(tmp_path / "python.exe"))
    monkeypatch.setattr(runtime, "resolve_profile_python", lambda *a: str(tmp_path / "python.exe"))
    monkeypatch.setattr(translator, "_validate_cpu_asr_runtime", lambda *a: None)
    monkeypatch.setattr(translator, "_get_supported_cli_args", lambda *a: None)
    if current:
        registry(tmp_path, runtime.HAAS_MODEL_ID)
    context = translator.TranslationContext({"asr_compute_backend": "cpu", "runtime_profile": "cpu",
        "use_nemo_asr": use_nemo, "nemo_asr_model": model, "model": runtime.HAAS_MODEL_ID}, "test")
    assert context._build_command()


@pytest.mark.parametrize("profile", ["cuda", "rocm", "cpu"])
def test_download_refuses_before_http(monkeypatch, tmp_path, profile):
    monkeypatch.setattr(downloads.sys, "frozen", True, raising=False)
    monkeypatch.setattr(downloads, "get_packaged_runtime_profile", lambda: profile)
    monkeypatch.setattr(downloads, "resolve_profile_python", lambda *a: str(tmp_path / "python.exe"))
    http = Mock(side_effect=AssertionError("must not download"))
    monkeypatch.setattr(downloads, "HttpDownloader", http)
    manager = downloads.ModelDownloadManager()
    with pytest.raises(ValueError) as error:
        asyncio.run(manager.start_download("parakeet-ctc-ja", runtime.HAAS_MODEL_ID, "cpu"))
    assert str(error.value) == runtime.haas_runtime_update_message(profile)
    assert not manager._tasks
    http.assert_not_called()


@pytest.mark.parametrize("frozen,installed,current,model", [
    (True, False, False, runtime.HAAS_MODEL_ID),
    (True, True, True, runtime.HAAS_MODEL_ID),
    (False, True, False, runtime.HAAS_MODEL_ID),
    (True, True, False, "nvidia/parakeet-tdt-0.6b-v3"),
])
def test_download_compatibility_exemptions(monkeypatch, tmp_path, frozen, installed, current, model):
    monkeypatch.setattr(downloads.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(downloads, "get_packaged_runtime_profile", lambda: "cpu")
    monkeypatch.setattr(downloads, "resolve_profile_python", lambda *a: str(tmp_path / "python.exe") if installed else None)
    if current:
        registry(tmp_path, runtime.HAAS_MODEL_ID)
    manager = downloads.ModelDownloadManager()
    async def worker(*args):
        pass
    monkeypatch.setattr(manager, "_run_download_task", worker)
    async def run():
        task = await manager.start_download("parakeet-ctc-ja", model, "cpu")
        await manager._workers[task]
        assert task in manager._tasks
    asyncio.run(run())


@pytest.mark.parametrize("profile,folder", [("cpu", "_runtime"), ("cuda", "_runtime_cpu_asr"), ("rocm", "_runtime_cpu_asr")])
def test_resolver_selects_packaged_cpu_runtime(monkeypatch, tmp_path, profile, folder):
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime.sys, "executable", str(tmp_path / "app.exe"))
    python = tmp_path / folder / "python.exe"
    python.parent.mkdir()
    python.touch()
    assert Path(runtime.resolve_profile_python(profile, "cpu")) == python


@pytest.mark.parametrize("profile", ["cuda", "rocm", "cpu"])
def test_start_update_message_for_old_runtime(monkeypatch, tmp_path, profile):
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    resolver = Mock(return_value=str(tmp_path / "python.exe"))
    monkeypatch.setattr(runtime, "resolve_profile_python", resolver)
    args = {"runtime_profile": profile, "asr_compute_backend": "cpu",
            "use_nemo_asr": True, "nemo_asr_model": runtime.HAAS_MODEL_ID}
    assert runtime.cpu_asr_start_update_message(args) == runtime.haas_runtime_update_message(profile)
    resolver.assert_called_once_with(profile, "cpu")


@pytest.mark.parametrize("overrides,frozen,installed,current", [
    ({}, False, True, False),
    ({"asr_compute_backend": "cuda"}, True, True, False),
    ({"asr_compute_backend": None}, True, True, False),
    ({"use_nemo_asr": False}, True, True, False),
    ({"nemo_asr_model": "other", "model": runtime.HAAS_MODEL_ID}, True, True, False),
    ({}, True, False, False),
    ({}, True, True, True),
])
def test_start_update_message_exemptions(monkeypatch, tmp_path, overrides, frozen, installed, current):
    monkeypatch.setattr(runtime.sys, "frozen", frozen, raising=False)
    monkeypatch.setattr(runtime, "resolve_profile_python",
                        lambda *a: str(tmp_path / "python.exe") if installed else None)
    if current:
        registry(tmp_path, runtime.HAAS_MODEL_ID)
    args = {"runtime_profile": "cpu", "asr_compute_backend": "cpu",
            "use_nemo_asr": True, "nemo_asr_model": runtime.HAAS_MODEL_ID}
    args.update(overrides)
    assert runtime.cpu_asr_start_update_message(args) is None


@pytest.mark.parametrize("profile", ["cuda", "rocm", "cpu"])
def test_url_start_returns_runtime_update_400(monkeypatch, tmp_path, profile):
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.api import translation as api

    args = {"url": "https://example.com/live", "runtime_profile": profile,
            "asr_compute_backend": "cpu", "use_nemo_asr": True,
            "nemo_asr_model": runtime.HAAS_MODEL_ID}
    manager = Mock()
    manager.get_config.return_value = {
        "input": {}, "transcription": {"backend": "parakeet-ctc-ja", "asr_compute_backend": "cpu"},
        "translation": {}, "output_notification": {}, "runtime": {"profile": profile},
    }
    manager.to_main_args.return_value = args
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    monkeypatch.setattr(runtime.sys, "frozen", True, raising=False)
    monkeypatch.setattr(runtime, "resolve_profile_python", lambda *a: str(tmp_path / "python.exe"))
    create = Mock(side_effect=AssertionError("must not create task"))
    monkeypatch.setattr(api, "create_task", create)
    preflight = Mock(side_effect=AssertionError("must not build command for URL"))
    monkeypatch.setattr(translator.TranslationContext, "_build_command", preflight)
    request = api.StartTranslationRequest(audio_source="url", url=args["url"],
                                          nemo_asr_model=runtime.HAAS_MODEL_ID)
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.start_translation(request, SimpleNamespace(headers={})))
    assert error.value.status_code == 400
    assert error.value.detail == runtime.haas_runtime_update_message(profile)
    create.assert_not_called()
    preflight.assert_not_called()


def test_engine_fingerprint_returns_none_when_a_file_vanishes(tmp_path, monkeypatch):
    from backend.core import cpu_asr_runtime
    package = tmp_path / 'stream_translator_gpt'
    package.mkdir()
    (package / 'main.py').write_text('x', encoding='utf-8')
    monkeypatch.setattr(cpu_asr_runtime.Path, 'read_bytes', lambda self: (_ for _ in ()).throw(PermissionError('locked')))
    assert cpu_asr_runtime.engine_fingerprint(package) is None


def test_engine_fingerprint_cache_sees_same_size_older_mtime_change(tmp_path):
    import os
    from backend.core import cpu_asr_runtime
    package = tmp_path / 'stream_translator_gpt'
    package.mkdir()
    first, second = package / 'a.py', package / 'b.py'
    first.write_text('aa', encoding='utf-8')
    second.write_text('bb', encoding='utf-8')
    os.utime(first, ns=(1_000_000_000, 1_000_000_000))
    os.utime(second, ns=(2_000_000_000, 2_000_000_000))
    before = cpu_asr_runtime.engine_fingerprint(package)
    first.write_text('cc', encoding='utf-8')
    os.utime(first, ns=(1_500_000_000, 1_500_000_000))
    assert cpu_asr_runtime.engine_fingerprint(package) != before


def test_engine_fingerprint_ignores_rebuilt_dll_bytes_and_line_endings(tmp_path):
    from backend.core import cpu_asr_runtime
    copies = []
    for name, dll, source in (('a', b'MZ-stamp-1', b'x = 1\r\n'), ('b', b'MZ-stamp-2', b'x = 1\n')):
        package = tmp_path / name / 'stream_translator_gpt'
        (package / 'native').mkdir(parents=True)
        (package / 'native' / 'process_audio_capture.dll').write_bytes(dll)
        (package / 'main.py').write_bytes(source)
        copies.append(package)
    assert cpu_asr_runtime.engine_fingerprint(copies[0]) == cpu_asr_runtime.engine_fingerprint(copies[1])
    (copies[1] / 'native' / 'process_audio_capture.dll').unlink()
    assert cpu_asr_runtime.engine_fingerprint(copies[0]) != cpu_asr_runtime.engine_fingerprint(copies[1])
