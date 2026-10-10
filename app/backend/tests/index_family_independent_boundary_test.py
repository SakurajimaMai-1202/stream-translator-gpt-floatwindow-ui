"""Cross-layer tests owned independently from the family implementation."""

from backend.core.config_manager import ConfigManager
from backend.core.llm_translator import create_family_preview_client
from stream_translator_gpt.translation_policy import resolve_model_family


def _local_family_args(config_manager, family):
    config = config_manager.get_config()
    translation = config["translation"]
    translation.update({
        "enabled": True,
        "backend": "gpt",
        "translation_model_family": family,
        "use_smart_prompt": False,
        "translation_prompt": "翻譯成繁體中文",
        "translation_provider": "openai_compatible",
        "gpt_model": "Index-Translate-9B" if family == "index_translate" else "HY-MT2",
        "gpt_base_url": "http://127.0.0.1:1234/v1",
        "hy_mt2_optimizer_enabled": True,
        "hy_mt2_style_text": "HY PRIVATE STYLE",
        "index_translate_optimizer_enabled": True,
        "index_translate_style_text": "INDEX PRIVATE STYLE",
    })
    return config_manager.to_main_args(config)


def test_index_family_independent_config_args_only_enable_selected_family(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")

    index_args = _local_family_args(manager, "index_translate")
    hy_args = _local_family_args(manager, "hy_mt2")

    assert index_args["translation_model_family"] == "index_translate"
    assert index_args.get("index_translate_optimizer_enabled") is True
    # Both profiles remain independently persisted in the argument bundle;
    # the selected family decides which one the client applies.
    assert hy_args.get("index_translate_optimizer_enabled") is True
    assert hy_args["translation_model_family"] == "hy_mt2"
    assert hy_args.get("hy_mt2_optimizer_enabled") is True

    index_client = create_family_preview_client(index_args, optimized=True)
    hy_client = create_family_preview_client(hy_args, optimized=True)
    assert index_client.model_family == "index_translate"
    assert index_client.prompt_strategy.optimizer_settings.style_text == "INDEX PRIVATE STYLE"
    assert hy_client.model_family == "hy_mt2"
    assert hy_client.prompt_strategy.optimizer_settings.style_text == "HY PRIVATE STYLE"


def test_index_family_independent_preview_client_uses_only_selected_family_settings(tmp_path):
    import json

    manager = ConfigManager(tmp_path / "config.yaml")
    args = _local_family_args(manager, "index_translate")
    args["index_translate_aliases"] = json.dumps({"ミオ": "大神澪"}, ensure_ascii=False)
    args["hy_mt2_aliases"] = json.dumps({"ミオ": "HY錯誤譯名"}, ensure_ascii=False)
    glossary_folder = tmp_path / "index_terms"
    glossary_folder.mkdir()
    args["index_translate_glossary_folder"] = str(glossary_folder)
    client = create_family_preview_client(args, optimized=True)

    request, prepared = client.prepare_translation_request(
        "ミオが来た", candidates={"ミオ": "候補譯名"}
    )

    assert client.model_family == "index_translate"
    assert client.prompt_strategy.optimizer_settings.style_text == "INDEX PRIVATE STYLE"
    assert request.candidates == {"ミオ": "候補譯名"}
    assert request.glossary["ミオ"] == "大神澪"
    assert "【源文】" in prepared.user_content
    assert "不确定" in prepared.user_content

    basic = create_family_preview_client(args, optimized=False)
    assert basic.model_family == "index_translate"
    assert basic.family_optimizer_enabled is False
    assert basic.base_url == "http://127.0.0.1:1234/v1"
    assert basic.api_key == "114514"
    assert "HY錯誤譯名" not in basic.glossary.values()


def test_index_family_independent_basic_preview_still_uses_family_strategy(tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.yaml")
    args = _local_family_args(manager, "index_translate")
    client = create_family_preview_client(args, optimized=False)
    seen = {}

    def fake_translate(task):
        prepared = client._prepare_prompt(task)
        seen["request"] = task._family_request
        seen["prompt"] = prepared.user_content
        task.translation = "測試譯文"
        task.translation_failed = False

    monkeypatch.setattr(client, "translate", fake_translate)
    result = client.translate_preview("こんにちは")

    assert result["translation"] == "測試譯文"
    assert seen["request"].source_text == "こんにちは"
    assert "こんにちは" in seen["prompt"]


def test_index_family_independent_preview_variants_share_glossary_diagnostics(tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.yaml")
    args = _local_family_args(manager, "index_translate")
    diagnostic_glossary = {"ミオ": "大神澪", "無關詞": "不應命中"}
    outputs = []

    for optimized in (False, True):
        client = create_family_preview_client(args, optimized=optimized)

        def fake_translate(task, preview_client=client):
            preview_client._prepare_prompt(task)
            task.translation = "大神澪來了。"
            task.translation_failed = False

        monkeypatch.setattr(client, "translate", fake_translate)
        result = client.translate_preview("ミオが来た", diagnostic_glossary=diagnostic_glossary)
        outputs.append(result)
        client.close()

    assert outputs[0]["glossary_hits"] == outputs[1]["glossary_hits"] == {"ミオ": "大神澪"}
    assert outputs[0]["validation_enforced"] is False
    assert outputs[1]["validation_enforced"] is True


def test_index_family_independent_api_preview_keeps_selected_family(monkeypatch):
    import asyncio
    import backend.api.translation as translation_api

    class ConfigManagerStub:
        def get_config(self):
            return {"translation": {"backend": "gpt"}}

        def to_main_args(self, config):
            return {
                "translation_model_family": config["translation"]["translation_model_family"],
                "translation_provider": "openai_compatible",
                "gpt_model": "Index-Translate-9B",
                "index_translate_optimizer_enabled": True,
                "hy_mt2_optimizer_enabled": True,
            }

    created = []

    class PreviewClient:
        model_family = "index_translate"

        def translate_preview(self, text, context, glossary=None):
            return {"translation": "譯文", "error": None, "latency_ms": 1}

        def close(self):
            pass

    def create_client(args, optimized):
        created.append((args["translation_model_family"], optimized))
        return PreviewClient()

    monkeypatch.setattr(translation_api, "get_config_manager", lambda: ConfigManagerStub())
    monkeypatch.setattr(
        "backend.core.llm_translator.create_family_preview_client", create_client
    )
    response = asyncio.run(translation_api.preview_translation(
        translation_api.FamilyPreviewRequest(
            text="こんにちは",
            config={"translation": {"translation_model_family": "index_translate"}},
        )
    ))

    assert response["family"] == "index_translate"
    assert created == [("index_translate", False), ("index_translate", True)]


def test_index_family_independent_auto_detection_matches_core_for_model_aliases(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    cases = {
        "Index-Translate-9B": "index_translate",
        "IndexTranslate-9B": "index_translate",
        "HY-MT2-7B": "hy_mt2",
        "HyMT2-7B": "hy_mt2",
        "hymt2-7b": "hy_mt2",
    }

    for model_name, expected_family in cases.items():
        config = manager.get_config()
        config["translation"].update({
            "enabled": True,
            "backend": "gpt",
            "translation_model_family": "auto",
            "gpt_model": model_name,
            "use_smart_prompt": False,
        })
        args = manager.to_main_args(config)
        runtime_family = resolve_model_family(
            args.get("translation_model_family"), args.get("gpt_model"),
            args.get("translation_provider", "openai_compatible"),
        )
        assert runtime_family == expected_family, (model_name, args.get("translation_model_family"))


def test_index_family_independent_local_api_selection_overrides_gemini_backend(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({
        "enabled": True,
        "backend": "gemini",
        "gemini_model": "gemini-configured-model",
        "translation_model_family": "index_translate",
        "index_translate_optimizer_enabled": True,
        "index_translate_provider": "lm_studio",
        "index_translate_lm_studio_url": "http://127.0.0.1:1234/v1",
        "index_translate_lm_studio_model": "Index-Translate-9B-Q4_K_M",
        "use_smart_prompt": False,
        "translation_prompt": "翻譯成繁體中文",
    })
    args = manager.to_main_args(config)

    from stream_translator_gpt.pipeline_runner import create_translator
    translator = create_translator(args)
    client = translator.llm_client

    assert args["translation_provider"] == "lm_studio"
    assert args["gpt_model"] == "Index-Translate-9B-Q4_K_M"
    assert client.llm_type == client.LLM_TYPE.GPT
    assert client.model == "Index-Translate-9B-Q4_K_M"
    assert client.provider == "lm_studio"
    assert client.model_family == "index_translate"
