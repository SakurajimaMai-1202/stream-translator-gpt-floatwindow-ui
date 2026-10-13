import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.api import llama as llama_api
from backend.core.llama_manager import LlamaManager
from stream_translator_gpt.translation_output import TranslationOutputConversionError


def test_llama_manager_normalizes_translation_output(monkeypatch):
    manager = LlamaManager()
    manager.is_running = True

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": "简体中文"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("backend.core.llama_manager.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(
        "stream_translator_gpt.translation_output.normalize_translation_output",
        lambda text, target: text.replace("简体", "繁體") if target == "Traditional Chinese" else text,
    )

    assert asyncio.run(manager.translate("source")) == "繁體中文"


def test_llama_route_clears_output_and_reports_conversion_error(monkeypatch):
    monkeypatch.setattr(llama_api.llama_state, "is_running", True)
    monkeypatch.setattr(llama_api.llama_state, "current_model", "test-model")
    monkeypatch.setattr(
        llama_api.asyncio, "to_thread", lambda function, *_args, **_kwargs: asyncio.sleep(0, result={}),
    )

    async def fake_inference(_request):
        return {"text": "简体中文"}

    monkeypatch.setattr(llama_api, "inference", fake_inference)
    monkeypatch.setattr(
        "stream_translator_gpt.translation_output.normalize_translation_output",
        lambda *_args: (_ for _ in ()).throw(TranslationOutputConversionError("OpenCC unavailable")),
    )

    result = asyncio.run(llama_api.translate_with_llama(llama_api.TranslateRequest(text="source")))

    assert result["translated"] == ""
    assert result["error"] == "OpenCC unavailable"


def test_llama_route_normalizes_translation_output(monkeypatch):
    monkeypatch.setattr(llama_api.llama_state, "is_running", True)
    monkeypatch.setattr(llama_api.llama_state, "current_model", "test-model")
    monkeypatch.setattr(
        llama_api.asyncio, "to_thread", lambda function, *_args, **_kwargs: asyncio.sleep(0, result={}),
    )

    async def fake_inference(_request):
        return {"text": "简体中文"}

    monkeypatch.setattr(llama_api, "inference", fake_inference)
    monkeypatch.setattr(
        "stream_translator_gpt.translation_output.normalize_translation_output",
        lambda text, _target: text.replace("简体", "繁體"),
    )

    result = asyncio.run(llama_api.translate_with_llama(llama_api.TranslateRequest(text="source")))

    assert result["translated"] == "繁體中文"
    assert "error" not in result


def test_lightweight_translation_output_import_does_not_load_numpy():
    import subprocess

    package_root = Path(__file__).resolve().parents[3] / "stream-translator-gpt"
    code = (
        "import sys; "
        "from stream_translator_gpt.translation_output import normalize_translation_output; "
        "assert 'numpy' not in sys.modules"
    )
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=package_root,
        check=True,
        capture_output=True,
        text=True,
    )