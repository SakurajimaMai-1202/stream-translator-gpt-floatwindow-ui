"""Offline regressions for ASR conversion failures and Gemini timeouts."""

import queue
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from stream_translator_gpt import audio_transcriber, llm_translator
from stream_translator_gpt.common import TranslationTask


@pytest.mark.parametrize("error", [
    RuntimeError("Traditional/Simplified Chinese Qwen3-ASR output requires OpenCC."),
    ValueError("conversion failed"),
])
def test_asr_conversion_failure_clears_output_warns_once_and_recovers(monkeypatch, capsys, error):
    class FakeTranscriber(audio_transcriber.AudioTranscriber):
        def transcribe(self, audio, initial_prompt=None):
            return "simplified source", None

    conversions = iter([error, error, "converted output"])

    def convert(text, language):
        assert language == "zh-tw"
        result = next(conversions)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(audio_transcriber, "normalize_chinese_script", convert)
    transcriber = FakeTranscriber(asr_output_language="zh-tw")
    incoming, outgoing = queue.SimpleQueue(), queue.SimpleQueue()
    tasks = [TranslationTask(np.zeros(0, dtype=np.float32), (0, 1)) for _ in range(3)]
    for task in tasks:
        incoming.put(task)
    incoming.put(None)

    transcriber.loop(incoming, outgoing)

    for task in tasks[:2]:
        assert task.raw_transcript == ""
        assert task.transcript == ""
        assert task.latency_trace.asr_finished_at is not None
    assert outgoing.get_nowait() is tasks[2]
    assert tasks[2].transcript == "converted output"
    assert outgoing.get_nowait() is None
    assert outgoing.empty()
    assert capsys.readouterr().err.count("ASR script conversion failed") == 1


def install_fake_gemini(monkeypatch, outcomes):
    calls = []
    google = ModuleType("google")
    genai = ModuleType("google.genai")
    types = ModuleType("google.genai.types")
    for name in ("GenerateContentConfig", "ThinkingConfig", "SafetySetting"):
        setattr(types, name, lambda **kwargs: SimpleNamespace(**kwargs))

    class Client:
        def __init__(self, **kwargs):
            self.options = kwargs["http_options"]
            self.models = self

        def generate_content(self, **kwargs):
            calls.append((self.options, kwargs))
            result = next(outcomes)
            if isinstance(result, Exception):
                raise result
            return SimpleNamespace(text=result)

    genai.Client = Client
    genai.types = types
    google.genai = genai
    monkeypatch.setitem(sys.modules, "google", google)
    monkeypatch.setitem(sys.modules, "google.genai", genai)
    monkeypatch.setitem(sys.modules, "google.genai.types", types)
    monkeypatch.setattr(llm_translator.ApiKeyPool, "use_google_api", lambda: None)
    return calls


@pytest.mark.parametrize("request_timeout", [30.0, 2.75])
def test_gemini_timeout_records_failure_releases_slot_and_retries(monkeypatch, request_timeout):
    calls = install_fake_gemini(monkeypatch, iter([TimeoutError("request timed out"), "translated output"]))
    client = llm_translator.LLMClient(
        llm_type="Gemini", model="gemini-test", prompt="Translate to English",
        history_size=2, proxy="http://proxy.invalid", use_json_result=False,
        gemini_base_url="https://gemini.invalid", translation_target_language="English",
        request_timeout=request_timeout,
    )
    translator = llm_translator.ParallelTranslator(
        client, timeout=60, retry_if_translation_fails=True, max_concurrency=1,
    )
    task = TranslationTask(np.zeros(0, dtype=np.float32), (0, 1))
    task.transcript = "source"
    translator.processing_queue.append(task)

    translator._trigger(task)
    event, completed = translator._scheduler_events.get(timeout=5)
    assert (event, completed) == ("completed", task)
    assert not task._translation_inflight
    assert task._translation_attempts == 1
    assert task.translation_failed
    assert task.translation == ""
    assert task.translation_error == "request timed out"
    assert task.translation_validation_reasons == ("translation_request_failed", "empty_output")
    assert not task.translation_validation_rejected
    assert not client.history_pairs

    translator._retrigger_failed_tasks()
    event, completed = translator._scheduler_events.get(timeout=5)
    assert (event, completed) == ("completed", task)
    assert task._translation_attempts == 2
    assert not task._translation_inflight
    assert not task.translation_failed
    assert task.translation == "translated output"
    assert list(client.history_pairs) == [("source", "translated output")]
    assert len(calls) == 2
    for options, _ in calls:
        assert options["timeout"] == int(request_timeout * 1000)
        assert options["client_args"] == {"proxy": "http://proxy.invalid"}
        assert options["base_url"] == "https://gemini.invalid"
