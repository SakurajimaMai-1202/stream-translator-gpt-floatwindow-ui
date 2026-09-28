from stream_translator_gpt.hy_mt2_optimizer import OptimizerSettings, build_prompt
from stream_translator_gpt.translation_policy import TranslationRequest, create_prompt_strategy
from stream_translator_gpt.llm_translator import LLMClient, LMStudioProvider, LlamaCppProvider, ParallelTranslator
from stream_translator_gpt.hy_mt2_glossary import load_glossary_folder
from stream_translator_gpt.hy_mt2_context import SourceContext
from stream_translator_gpt.hy_mt2_output_validation import repeats_previous_translation
from stream_translator_gpt.common import TranslationTask
from datetime import datetime, timezone
import numpy as np


def test_optimizer_limits_context_and_terms():
    settings = OptimizerSettings(context_window=3, max_context_chars=8, max_terms=1)
    result = build_prompt(
        "すいちゃんとみこち", "繁體中文翻譯", {"すいちゃん": "Suisei", "みこち": "Miko"},
        ("很舊的一句", "太長的前文句子", "上一句", "這一句"), settings,
    )
    assert "すいちゃん 翻譯成 Suisei" in result
    assert "みこち 翻譯成 Miko" not in result
    assert "上一句\n這一句" in result
    assert "太長的前文句子" not in result
    assert result.endswith("すいちゃんとみこち")


def test_optimizer_is_opt_in_to_hy_mt2_strategy():
    strategy = create_prompt_strategy("hy_mt2", "翻譯", "text")
    request = TranslationRequest(1, "すいちゃん", glossary={"すいちゃん": "Suisei"})
    old = strategy.prepare(request).user_content
    strategy.optimizer_settings = OptimizerSettings(style_text="台灣繁中字幕")
    new = strategy.prepare(request).user_content
    assert "参考下面的翻译" in old
    assert "〖翻譯要求〗" in new
    assert "〖術語〗" in new


def test_aliases_apply_only_to_enabled_hy_mt2():
    common = dict(llm_type=LLMClient.LLM_TYPE.GPT, model="localllm", prompt="翻譯",
                  history_size=3, proxy=None, use_json_result=False,
                  glossary={"星街すいせい": "Suisei"},
                  hy_mt2_aliases='{"すいちゃん":"Suisei"}',
                  provider="openai_compatible")
    optimized = LLMClient(**common, model_family="hy_mt2", hy_mt2_optimizer_enabled=True)
    disabled = LLMClient(**common, model_family="hy_mt2", hy_mt2_optimizer_enabled=False)
    other = LLMClient(**common, model_family="generic_chat", hy_mt2_optimizer_enabled=True)
    assert optimized.glossary["すいちゃん"] == "Suisei"
    assert "すいちゃん" not in disabled.glossary
    assert "すいちゃん" not in other.glossary


def test_local_server_adapters_share_prompt_path():
    for provider, adapter in (("lm_studio", LMStudioProvider), ("llama_cpp", LlamaCppProvider)):
        client = LLMClient(llm_type=LLMClient.LLM_TYPE.GPT, model="localllm", prompt="翻譯",
                           history_size=0, proxy=None, use_json_result=False,
                           model_family="hy_mt2", provider=provider,
                           hy_mt2_optimizer_enabled=True)
        assert isinstance(client.provider_adapter, adapter)
        assert client.prompt_strategy.optimizer_settings.context_window == 3


def test_json_glossary_loads_exact_terms_and_aliases(tmp_path):
    (tmp_path / "hololive.json").write_text(
        '{"星街すいせい":{"target":"Suisei","aliases":["すいちゃん"]}}', encoding="utf-8")
    assert load_glossary_folder(str(tmp_path)) == {
        "星街すいせい": "Suisei", "すいちゃん": "Suisei"}


def test_source_context_snapshot_is_bounded_and_immutable():
    context = SourceContext(2)
    context.append("A")
    snapshot = context.snapshot()
    context.append("B")
    context.append("C")
    assert snapshot == ("A",)
    assert context.snapshot() == ("B", "C")


def test_context_echo_from_short_fragment_is_rejected_without_changing_valid_repetition():
    history = (("まだ誰も見たことのない景色を一緒に作りに行こう",
                "我們一起去創造還沒有人看過的景色吧。"),)
    contaminated = "一起去創造還沒有人見過的景色吧。  \n在交會之處"
    assert repeats_previous_translation("新たな未来", contaminated, history)
    assert not repeats_previous_translation("まだ誰も見たことのない景色を一緒に作りに行こう",
                                            contaminated, history)
    assert not repeats_previous_translation("新たな未来", "新的未來", history)

    client = LLMClient(llm_type=LLMClient.LLM_TYPE.GPT, model="hy-mt2-7b-i1",
                       prompt="翻譯", history_size=3, proxy=None, use_json_result=False,
                       model_family="hy_mt2", provider="openai_compatible",
                       hy_mt2_optimizer_enabled=True)
    client._append_history_message(*history[0])
    task = TranslationTask(np.zeros(1), (0.0, 1.0))
    task.transcript = "新たな未来"
    task.translation = contaminated
    assert client._validate_hy_mt2_output(task) == "context_echo_rejected"
    assert task.translation == ""
    assert task.translation_validation_rejected
    assert client.hy_mt2_context.snapshot() == (history[0][0],)
    task.llm_latency_ms = 10.0
    task._translation_attempts = 1
    task.start_time = datetime.now(timezone.utc)
    scheduler = ParallelTranslator(client, timeout=10, retry_if_translation_fails=True)
    scheduler.processing_queue.append(task)
    scheduler._retrigger_failed_tasks()
    assert task._translation_attempts == 1
    assert scheduler._get_results() == [task]
