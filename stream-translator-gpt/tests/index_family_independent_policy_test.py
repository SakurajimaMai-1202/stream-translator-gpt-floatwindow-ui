"""Independent contract checks for the Index-Translate family plan."""

from stream_translator_gpt.hy_mt2_optimizer import OptimizerSettings
from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.llm_translator import LLMClient
from stream_translator_gpt.translation_policy import (
    TranslationRequest,
    create_prompt_strategy,
    get_capabilities,
    resolve_model_family,
    validate_translation,
)


def test_index_family_independent_detection_and_manual_override():
    assert resolve_model_family("auto", "Index-Translate-9B-Q4_K_M", "openai_compatible") == "index_translate"
    assert resolve_model_family("index", "opaque-quant", "openai_compatible") == "index_translate"
    assert resolve_model_family("auto", "opaque-quant", "openai_compatible") == "generic_chat"


def test_index_family_independent_uses_single_user_insttrans_prompt_and_standard_params():
    capabilities = get_capabilities("index_translate")
    strategy = create_prompt_strategy("index_translate", "翻譯成繁體中文", "json")
    strategy.optimizer_settings = OptimizerSettings()
    prepared = strategy.prepare(TranslationRequest(
        segment_id=1,
        source_text="今日は配信です。",
        glossary={"配信": "直播"},
    ))

    assert prepared.system_instruction is None
    assert "【源文】" in prepared.user_content
    assert "只输出译文" in prepared.user_content
    assert prepared.output_format == "text"
    assert prepared.temperature == 0
    assert prepared.top_p == 1
    assert prepared.top_k is None
    assert capabilities.supports_structured_output is False


def test_index_family_independent_separates_fixed_terms_from_uncertain_candidates():
    strategy = create_prompt_strategy("index_translate", "翻譯成繁體中文", "text")
    strategy.optimizer_settings = OptimizerSettings()
    request = TranslationRequest(
        segment_id=2,
        source_text="ミオが来た",
        glossary={"ミオ": "大神澪"},
        candidates={"ミオ": "可能是 Mio"},
    )

    prompt = strategy.prepare(request).user_content
    assert "【硬性要求】" in prompt and "ミオ→大神澪" in prompt
    assert "【注意】" in prompt and "不确定" in prompt and "可能是 Mio" in prompt


def test_index_family_independent_does_not_demand_unrelated_fixed_glossary_entries():
    request = TranslationRequest(
        segment_id=3,
        source_text="今日は配信です。",
        glossary={"無関係な用語": "固定譯名"},
    )
    codes = {issue.code for issue in validate_translation(request, "今天是直播。")}
    assert "fixed_term_missing" not in codes


def test_index_family_independent_repeated_speech_is_not_rejected_as_context_echo():
    request = TranslationRequest(segment_id=4, source_text="もう一度お願いします。")
    history = (("もう一度お願いします。", "請再說一次，麻煩你。"),)
    assert "context_echo_rejected" not in {
        issue.code for issue in validate_translation(request, "請再說一次，麻煩你。", history)
    }


def test_index_family_independent_optimizer_settings_do_not_leak_from_hy_mt2():
    client = LLMClient(
        LLMClient.LLM_TYPE.GPT, "Index-Translate-9B", "translate", 3, "", False,
        provider="openai_compatible", model_family="index_translate",
        hy_mt2_optimizer_enabled=True, hy_mt2_style_text="HY ONLY",
        index_translate_optimizer_enabled=True, index_translate_style_text="INDEX ONLY",
    )

    assert client.family_optimizer_enabled
    assert client.prompt_strategy.optimizer_settings.style_text == "INDEX ONLY"


def test_index_family_independent_openai_compatible_payload_has_no_vllm_extras(monkeypatch):
    class Completion:
        class Choice:
            class Message:
                content = "今天是直播。"
            message = Message()
        choices = [Choice()]

    captured = {}

    class Completions:
        @staticmethod
        def create(**kwargs):
            captured.update(kwargs)
            return Completion()

    class Chat:
        completions = Completions()

    class Client:
        chat = Chat()

    client = LLMClient(
        LLMClient.LLM_TYPE.GPT, "Index-Translate-9B", "translate", 0, "", False,
        provider="openai_compatible", model_family="index_translate",
        index_translate_optimizer_enabled=True,
    )
    client.api_key = "test-key"
    client._openai_clients["test-key"] = Client()
    task = TranslationTask(None, (0, 0))
    task.transcript = "今日は配信です。"
    client._translate_by_gpt(task)

    assert task.translation == "今天是直播。"
    assert captured["model"] == "Index-Translate-9B"
    assert captured["temperature"] == 0
    assert captured["top_p"] == 1
    assert "messages" in captured
    assert "extra_body" not in captured
    assert "enable_thinking" not in captured
    assert "chat_template_kwargs" not in captured
