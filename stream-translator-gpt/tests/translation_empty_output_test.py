from types import SimpleNamespace

import numpy as np
import pytest

from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.llm_translator import LLMClient, ParallelTranslator


@pytest.mark.parametrize("output", ["", " \n\t", "<unk>"])
@pytest.mark.parametrize("provider", ["fake", "openai", "gemini"])
@pytest.mark.parametrize("family", ["generic_chat", "hy_mt2", "index_translate"])
@pytest.mark.parametrize("retry", [False, True])
def test_empty_output_releases_queue_and_preserves_source(monkeypatch, output, provider, family, retry):
    calls = []

    def response(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(
            text=output,
            choices=[SimpleNamespace(message=SimpleNamespace(content=output))],
            usage=None,
        )

    client = LLMClient(
        "Gemini" if provider == "gemini" else "GPT", "custom", "Translate", 0, None, False,
        provider="gemini" if provider == "gemini" else "openai_compatible",
        model_family=family, output_format="text", api_key="test-key",
        hy_mt2_optimizer_enabled=family == "hy_mt2",
        index_translate_optimizer_enabled=family == "index_translate",
    )
    if provider == "fake":
        class Provider:
            def translate(self, client, task):
                task.translation = response().text
        client.provider_adapter = Provider()
    elif provider == "openai":
        monkeypatch.setattr("openai.OpenAI", lambda **kwargs: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=response))))
        monkeypatch.setattr("httpx.Client", lambda **kwargs: None)
    else:
        monkeypatch.setattr("stream_translator_gpt.llm_translator.ApiKeyPool.use_google_api", lambda: None)
        monkeypatch.setattr("google.genai.Client", lambda **kwargs: SimpleNamespace(
            models=SimpleNamespace(generate_content=response)))

    task = TranslationTask(np.zeros(512, dtype=np.float32), (0.0, 1.0))
    task.transcript = "source subtitle"
    translator = ParallelTranslator(client, timeout=0, retry_if_translation_fails=retry)
    translator.processing_queue.append(task)
    translator._trigger(task)
    assert translator._scheduler_events.get(timeout=2) == ("completed", task)
    assert task.translation_failed
    assert task.translation == ""
    assert task.llm_latency_ms is not None
    assert task.translation_error == "empty_output"

    if retry:
        assert translator._get_results() == []
        translator._retrigger_failed_tasks()
        assert translator._scheduler_events.get(timeout=2) == ("completed", task)
        translator._retrigger_failed_tasks()

    assert len(calls) == (2 if retry else 1)
    assert task._translation_attempts == len(calls)
    assert task.translation_failed
    assert task.translation_result.translation == ""
    assert task.llm_latency_ms is not None
    assert translator._get_results() == [task]
    assert task.transcript == "source subtitle"
    assert not translator.processing_queue
