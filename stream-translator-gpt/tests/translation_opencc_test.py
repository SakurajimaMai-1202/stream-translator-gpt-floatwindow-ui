import numpy as np
import pytest

from stream_translator_gpt.common import TranslationTask
from stream_translator_gpt.llm_translator import LLMClient, normalize_translation_output


@pytest.mark.parametrize("provider,model", [
    ("openai", "gpt"), ("gemini", "gemini"),
    ("openai_compatible", "custom"), ("lm_studio", "gemma"),
    ("llama_cpp", "HY-MT2"),
])
@pytest.mark.parametrize("target,prompt", [
    ("Traditional Chinese", "custom prompt"),
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
    assert task.translation == "這個軟體裡面有簡體中文，後臺正在執行。"
    assert task.translation_result.translation == task.translation
    assert not task.translation_failed


def test_other_targets_are_unchanged():
    for target in ("Japanese", "English", "Simplified Chinese", None):
        assert normalize_translation_output("软件", target) == "软件"


def test_conversion_failure_does_not_publish_raw_text(monkeypatch):
    client = LLMClient("GPT", "custom", "翻譯成繁體中文", 0, None, False)
    class Provider:
        def translate(self, client, task):
            task.translation = "简体中文"
    client.provider_adapter = Provider()
    def fail(*args):
        raise RuntimeError("OpenCC unavailable")
    monkeypatch.setattr("stream_translator_gpt.llm_translator.normalize_chinese_script", fail)
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
    assert asyncio.run(translator.translate("source")) == "這個軟體"


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
