import numpy as np
import pytest

from stream_translator_gpt.qwen3_asr_postprocess import (
    is_traditional_chinese_target,
    normalize_chinese_script,
    normalize_translation_script,
)
from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.llm_translator import LLMClient, normalize_translation_output


@pytest.mark.parametrize("provider,model", [
    ("openai", "gpt"), ("gemini", "gemini"),
    ("openai_compatible", "custom"), ("lm_studio", "gemma"),
    ("llama_cpp", "HY-MT2"),
])
@pytest.mark.parametrize("target,prompt", [
    ("Traditional Chinese", "custom prompt"),
    *[(target, "custom prompt") for target in (
        "zh-Hant-TW", "zh-HK", "zh_TW", "zh-MO", "zh-Hant-HK",
        "Traditional Chinese (Taiwan)", "繁體中文（台灣）",
    )],
    *[(None, "Translate into " + target) for target in ("zh-hk", "zh_hk", "繁中", "正體中文")],
    ("zh-TW", "custom prompt"), ("zh_Hant", "custom prompt"),
    ("繁體中文", "custom prompt"), (None, "翻譯成繁體中文"),
])
def test_all_providers_normalize_before_publishing(provider, model, target, prompt):
    client = LLMClient(
        llm_type="Gemini" if provider == "gemini" else "GPT",
        model=model, prompt=prompt, history_size=0, proxy=None,
        use_json_result=False, provider=provider,
        translation_target_language=target,
    )
    class Provider:
        def translate(self, client, task):
            task.translation = "这个软件里面有简体中文，后台正在运行。"
    client.provider_adapter = Provider()
    task = TranslationTask(np.zeros(512, dtype=np.float32), (0.0, 1.0))
    client.translate(task)
    assert task.translation == "這個軟件裡面有簡體中文，後台正在運行。"
    assert task.translation_result.translation == task.translation
    assert not task.translation_failed


def test_other_targets_are_unchanged():
    for target in ("Japanese", "English", "Simplified Chinese", "zh-CN", "zh-Hans", "zh-SG", None):
        assert normalize_translation_output("软件", target) == "软件"


def test_conversion_failure_does_not_publish_raw_text(monkeypatch):
    client = LLMClient("GPT", "custom", "翻譯成繁體中文", 0, None, False)
    class Provider:
        def translate(self, client, task):
            task.translation = "简体中文"
    client.provider_adapter = Provider()
    def fail(*args):
        raise RuntimeError("OpenCC unavailable")
    monkeypatch.setattr("stream_translator_gpt.llm_translator.normalize_translation_script", fail)
    task = TranslationTask(np.zeros(512, dtype=np.float32), (0.0, 1.0))
    client.translate(task)
    assert task.translation == task.translation_result.translation == ""
    assert task.translation_failed
    assert "OpenCC unavailable" in task.translation_error


@pytest.mark.parametrize("engine", ["gpt", "gemini", "llama"])
def test_backend_async_translation_uses_opencc(engine):
    import asyncio
    from backend.core.llm_translator import LLMTranslator, TranslationEngine
    translator = LLMTranslator.__new__(LLMTranslator)
    translator.engine = TranslationEngine(engine)
    async def response(*args):
        return "这个软件"
    setattr(translator, "_translate_with_" + engine, response)
    assert asyncio.run(translator.translate("source")) == "這個軟件"


def test_config_passes_target_even_with_custom_prompt(tmp_path):
    from backend.core.config_manager import ConfigManager
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({
        "use_smart_prompt": False, "translation_prompt": "Custom instruction",
        "target_language": "Traditional Chinese",
    })
    args = manager.to_main_args(config)
    assert args["translation_target_language"] == "Traditional Chinese"


@pytest.mark.parametrize("target", [
    "zh-Hant-TW", "zh-HK", "zh_TW", "zh-MO", "zh-Hant-HK",
    "zh-HK-x-local", "zh-MO-x-local", "yue-Hant-HK",
    "Traditional Chinese (Taiwan)", "Chinese (Traditional Chinese)",
    "繁體中文（台灣）", "繁体中文", "繁體", "繁体",
])
def test_traditional_target_helper_and_asr_conversion(target):
    assert is_traditional_chinese_target(target)
    assert normalize_chinese_script("软件", target) == "軟體"


@pytest.mark.parametrize("text,expected", [
    ("溢出來", "溢出來"),
    ("數據化", "數據化"),
    ("類型", "類型"),
    ("要是只限定一段時間", "要是只限定一段時間"),
    ("就只有", "就只有"),
    ("舞台", "舞台"),
    ("一只猫", "一隻貓"),
    ("这只猫", "這隻貓"),
    ("两只手", "兩隻手"),
    ("只限定", "只限定"),
    ("头发", "頭髮"),
    ("后来", "後來"),
])
def test_translation_script_preserves_vocabulary(text, expected):
    assert normalize_translation_script(text, "zh-TW") == expected


def test_translation_script_skips_restoration_when_length_changes(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        "stream_translator_gpt.qwen3_asr_postprocess._opencc",
        lambda config: SimpleNamespace(convert=lambda text: "臺隻額外"),
    )
    assert normalize_translation_script("台只", "zh-TW") == "臺隻額外"


@pytest.mark.parametrize("target", [
    "zh-CN", "zh-Hans", "zh-Hans-CN", "zh-SG", "zh", "Chinese",
    "Simplified Chinese", "简体中文", "簡體中文", None, "",
])
def test_non_traditional_target_helper(target):
    assert not is_traditional_chinese_target(target)
    assert normalize_translation_output("软件", target) == "软件"


def test_unknown_prompt_does_not_default_to_traditional():
    client = LLMClient("GPT", "custom", "Translate this", 0, None, False)
    assert client.translation_target_language is None
    assert normalize_translation_output("软件", client.translation_target_language) == "软件"


@pytest.mark.parametrize("output,reason", [
    ("\u3010\u7ea6\u675f\u8981\u6c42\u3011\u8f6f\u4ef6", "prompt_leakage"),
    ("\u8f6f\u4ef6", None),
    ("\u8edf\u4ef6", None),
    ("missing", "fixed_term_missing"),
])
def test_optimizer_checks_raw_leaks_and_converted_glossary(output, reason):
    client = LLMClient("GPT", "HY-MT2", "custom", 0, None, False,
        translation_target_language="zh-Hant-TW", model_family="hy_mt2",
        hy_mt2_optimizer_enabled=True, glossary={"software": "\u8f6f\u4ef6"})
    class Provider:
        def translate(self, client, task):
            task.translation = output
            client._prepare_prompt(task)
            client._validate_hy_mt2_output(task)
    client.provider_adapter = Provider()
    task = TranslationTask(np.zeros(0, dtype=np.float32), (0, 1))
    task.transcript = "software"
    client.translate(task)
    if reason:
        assert reason in task.translation_validation_reasons
        assert task.translation == ""
    else:
        assert task.translation == "\u8edf\u4ef6"
        assert not task.translation_failed


def test_auditor_converts_glossary_targets(tmp_path):
    from types import SimpleNamespace
    from stream_translator_gpt.translation_glossary_auditor import TranslationGlossaryAuditor
    auditor = TranslationGlossaryAuditor({"software": "\u8f6f\u4ef6"}, enabled=True,
        audit_log_path=tmp_path / "audit.log", issues_path=tmp_path / "issues.json",
        normalize_output=lambda text: normalize_translation_output(text, "zh-Hant-HK"))
    try:
        result = auditor.audit(SimpleNamespace(transcript="software", translation="\u8edf\u4ef6"))
        assert result[0]["compliant"]
        assert not auditor._records
    finally:
        auditor._handler.close()


@pytest.mark.parametrize("family", ["hy_mt2", "index_translate"])
def test_validator_forwards_raw_reply_outside_converter(monkeypatch, family):
    client = LLMClient("GPT", "custom", "Translate", 0, None, False,
        model_family=family, translation_target_language="zh-Hant-TW",
        hy_mt2_optimizer_enabled=family == "hy_mt2",
        index_translate_optimizer_enabled=family == "index_translate")
    calls = []
    def convert(text, target):
        calls.append((text, target))
        return text
    monkeypatch.setattr("stream_translator_gpt.llm_translator.normalize_translation_output", convert)
    task = TranslationTask(np.zeros(0, dtype=np.float32), (0, 1))
    task.transcript = "source"
    task.translation = "answer"
    client._prepare_prompt(task)
    raw = "\u3010\u7ea6\u675f\u8981\u6c42\u3011 answer"
    assert client._validate_hy_mt2_output(task, raw) == "prompt_leakage"
    assert calls == [("answer", "zh-Hant-TW")]
    assert task.translation == ""
