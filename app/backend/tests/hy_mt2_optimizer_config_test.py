import json

from backend.core.config_manager import ConfigManager


def test_optimizer_aliases_and_options_reach_translator(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({
        "enabled": True,
        "use_smart_prompt": False,
        "translation_prompt": "翻譯",
        "hy_mt2_optimizer_enabled": True,
        "hy_mt2_context_window": 2,
    })
    config["terminology"].update({
        "use_terminology_glossary": True,
        "glossary_list": [{"original": "星街すいせい", "translated": "Suisei",
                           "aliases": ["すいちゃん"]}],
    })
    args = manager.to_main_args(config)
    assert args["hy_mt2_optimizer_enabled"] is True
    assert args["hy_mt2_context_window"] == 2
    assert json.loads(args["translation_glossary"]) == {"星街すいせい": "Suisei"}
    assert json.loads(args["hy_mt2_aliases"]) == {"すいちゃん": "Suisei"}


def test_local_provider_switch_preserves_prompt_configuration(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({
        "enabled": True,
        "hy_mt2_optimizer_enabled": True,
        "hy_mt2_lm_studio_url": "http://127.0.0.1:1234/v1",
        "hy_mt2_lm_studio_model": "model-a",
        "hy_mt2_llama_cpp_url": "http://127.0.0.1:8080/v1",
        "hy_mt2_llama_cpp_model": "model-b",
    })
    config["translation"]["hy_mt2_provider"] = "lm_studio"
    lm = manager.to_main_args(config)
    config["translation"]["hy_mt2_provider"] = "llama_cpp"
    llama = manager.to_main_args(config)
    assert (lm["translation_provider"], lm["gpt_base_url"], lm["gpt_model"]) == (
        "lm_studio", "http://127.0.0.1:1234/v1", "model-a")
    assert (llama["translation_provider"], llama["gpt_base_url"], llama["gpt_model"]) == (
        "llama_cpp", "http://127.0.0.1:8080/v1", "model-b")
    assert lm["translation_prompt"] == llama["translation_prompt"]
    assert lm["hy_mt2_context_window"] == llama["hy_mt2_context_window"]


def test_local_provider_requires_model_id(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({"enabled": True, "hy_mt2_optimizer_enabled": True,
                                  "hy_mt2_provider": "lm_studio", "hy_mt2_lm_studio_model": ""})
    try:
        manager.to_main_args(config)
    except ValueError as exc:
        assert "model ID" in str(exc)
    else:
        raise AssertionError("An unset model ID must not silently use another provider")


def test_relative_glossary_folder_resolves_from_config_location(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({"enabled": True, "hy_mt2_optimizer_enabled": True,
                                  "hy_mt2_glossary_folder": "data/glossary"})
    args = manager.to_main_args(config)
    assert args["hy_mt2_glossary_folder"] == str(tmp_path / "data" / "glossary")


def test_opt_in_glossary_preset_switches_without_replacing_user_terms(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({"enabled": True, "hy_mt2_optimizer_enabled": True})
    config["terminology"].update({
        "use_terminology_glossary": True,
        "glossary_list": [{"original": "ホロメン", "translated": "我的譯法", "aliases": []}],
    })
    assert "hy_mt2_aliases" not in manager.to_main_args(config)

    config["translation"]["hy_mt2_glossary_preset"] = "hololive_vtuber"
    hololive = json.loads(manager.to_main_args(config)["hy_mt2_aliases"])
    assert hololive["ホロメン"] == "Hololive 成員"
    assert "星街すいせい" in hololive
    assert "ウィッグ" not in hololive

    config["translation"]["hy_mt2_glossary_preset"] = "cosplay"
    cosplay = json.loads(manager.to_main_args(config)["hy_mt2_aliases"])
    assert "ウィッグ" in cosplay
    assert "星街すいせい" not in cosplay
    assert json.loads(manager.to_main_args(config)["translation_glossary"])["ホロメン"] == "我的譯法"


def test_glossary_scope_keeps_legacy_global_and_prefers_current_profile(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({"enabled": True, "hy_mt2_optimizer_enabled": True})
    config["terminology"].update({
        "use_terminology_glossary": True,
        "glossary_list": [
            {"original": "ホロメン", "translated": "原有全域譯法", "aliases": ["ホロのメンバー"]},
            {"original": "ホロメン", "translated": "情境譯法", "scope": "hololive_vtuber", "aliases": ["ホロのメンバー"]},
            {"original": "ウィッグ", "translated": "我的假髮譯法", "scope": "cosplay"},
        ],
    })
    default = manager.to_main_args(config)
    assert json.loads(default["translation_glossary"]) == {"ホロメン": "原有全域譯法"}
    assert "ウィッグ" not in json.loads(default["translation_glossary"])

    config["translation"]["hy_mt2_glossary_preset"] = "hololive_vtuber"
    hololive = manager.to_main_args(config)
    assert json.loads(hololive["translation_glossary"])["ホロメン"] == "情境譯法"
    assert json.loads(hololive["hy_mt2_aliases"])["ホロのメンバー"] == "情境譯法"

    config["translation"]["hy_mt2_glossary_preset"] = "cosplay"
    cosplay = manager.to_main_args(config)
    assert json.loads(cosplay["translation_glossary"])["ホロメン"] == "原有全域譯法"
    assert json.loads(cosplay["translation_glossary"])["ウィッグ"] == "我的假髮譯法"


def test_custom_glossary_scope_persists_and_only_activates_selected_terms(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    scope = "custom_12345678-1234-1234-1234-123456789abc"
    config["translation"].update({"enabled": True, "hy_mt2_optimizer_enabled": True,
                                  "hy_mt2_glossary_preset": scope})
    config["terminology"].update({
        "use_terminology_glossary": True,
        "custom_glossary_scopes": [{"value": scope, "label": "星街雜談"}],
        "glossary_list": [
            {"original": "共通", "translated": "全域"},
            {"original": "專有", "translated": "自訂", "scope": scope, "aliases": ["別名"]},
            {"original": "其他", "translated": "另一情境", "scope": "cosplay"},
        ],
    })
    manager.update_config(config)
    restored = ConfigManager(tmp_path / "config.yaml").get_config()
    assert restored["terminology"]["custom_glossary_scopes"] == [{"value": scope, "label": "星街雜談"}]
    selected = manager.to_main_args(restored)
    assert json.loads(selected["translation_glossary"]) == {"共通": "全域", "專有": "自訂"}
    assert json.loads(selected["hy_mt2_aliases"]) == {"別名": "自訂"}
    restored["translation"]["hy_mt2_glossary_preset"] = ""
    assert json.loads(manager.to_main_args(restored)["translation_glossary"]) == {"共通": "全域"}
