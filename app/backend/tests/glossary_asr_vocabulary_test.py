import json

import pytest

from backend.core.config_manager import ConfigManager
from backend.core.hy_mt2_glossary_presets import active_user_terms, glossary_asr_rules, glossary_hotwords


def _config(manager, backend, **terminology):
    config = manager.get_config()
    flags = {"use_qwen3_asr": "qwen3-asr", "use_faster_whisper": "faster-whisper",
             "use_sensevoice_asr": "sensevoice", "use_nemo_asr": "parakeet-ctc-ja"}
    config["transcription"].update({flag: name == backend for flag, name in flags.items()})
    config["transcription"].update({"backend": backend, "transcription_initial_prompt": "手打ち",
                                    "asr_correction_rules": [{"canonical": "すいちゃん", "aliases": ["スイちゃん", "らスイちゃ"]}]})
    config["translation"]["translation_glossary_scope"] = "cosplay"
    config["terminology"].update({"use_terminology_glossary": True, "glossary_to_asr_prompt": True, "glossary_list": [
        {"original": "リハさん", "translated": "Riha桑", "aliases": ["ツイハさん", "リハーサルさん"], "scope": "cosplay"},
        {"original": "らスイちゃ", "translated": "Sui醬", "scope": "all"},
        {"original": "別情境", "translated": "x", "aliases": ["別情况"], "scope": "hololive_vtuber"},
    ], **terminology})
    return config


def test_glossary_aliases_become_asr_corrections_after_manual_rules(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    # Corrections work for every engine, including ones without a prompt.
    rules = json.loads(manager.to_main_args(_config(manager, "qwen3-asr"))["asr_correction_rules"])
    assert rules[0] == {"canonical": "すいちゃん", "aliases": ["スイちゃん", "らスイちゃ"]}
    assert {"canonical": "リハさん", "aliases": ["ツイハさん", "リハーサルさん"]} in rules
    assert {"canonical": "マシュマロ", "aliases": ["マシュモロ", "マシモロ"]} in rules
    # Other scopes' rows stay out of this session.
    assert all(rule["canonical"] != "別情境" for rule in rules)


@pytest.mark.parametrize("backend, prompted", [("faster-whisper", True), ("qwen3-asr", False),
                                               ("sensevoice", False), ("parakeet-ctc-ja", False)])
def test_glossary_originals_reach_only_prompt_capable_asr(tmp_path, backend, prompted):
    manager = ConfigManager(tmp_path / "config.yaml")
    # Runtime profiles hide engines this machine lacks; the feed only cares about the name.
    manager._coerce_transcription_backend = lambda requested, capabilities: requested
    args = manager.to_main_args(_config(manager, backend))
    prompt = args["transcription_initial_prompt"]
    if prompted:
        words = prompt.split(", ")
        assert words[:2] == ["手打ち", "リハさん"]
        assert "マシュマロ" not in words and "マシモロ" not in words
        assert {"canonical": "マシュマロ", "aliases": ["マシュモロ", "マシモロ"]} in json.loads(args["asr_correction_rules"])
        # An original kept for a misheard spelling is not a hint.
        assert "らスイちゃ" not in words
    else:
        assert prompt == "手打ち"


def test_vocabulary_switches_turn_each_feed_off(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._coerce_transcription_backend = lambda requested, capabilities: requested
    assert manager.to_main_args(_config(manager, "faster-whisper"))["transcription_initial_prompt"] != "手打ち"
    args = manager.to_main_args(_config(manager, "faster-whisper", glossary_to_asr_corrections=False,
                                        glossary_to_asr_prompt=False))
    assert json.loads(args["asr_correction_rules"]) == [{"canonical": "すいちゃん", "aliases": ["スイちゃん", "らスイちゃ"]}]
    assert args["transcription_initial_prompt"] == "手打ち"
    config = _config(manager, "faster-whisper", use_terminology_glossary=False)
    assert manager.to_main_args(config)["transcription_initial_prompt"] == "手打ち"


def test_hotwords_stay_within_budget():
    terminology = {"glossary_list": [{"original": f"名前{i:02d}", "translated": "x"} for i in range(40)]}
    words = glossary_hotwords(terminology, "", max_chars=30)
    assert words == ["名前00", "名前01", "名前02", "名前03", "名前04"]
    assert glossary_asr_rules(terminology, "") == []



def test_aliases_cannot_expand_correct_originals():
    terminology = {"glossary_list": [
        {"original": "桜島麻衣", "aliases": ["麻衣", "桜島麻衣", "マイ", "別名"]},
        {"original": "マイ", "scope": "cosplay"}, {"original": "別名", "scope": "other"},
    ]}
    assert glossary_asr_rules(terminology, "cosplay")[0] == {"canonical": "桜島麻衣", "aliases": ["別名"]}


def test_all_scope_does_not_duplicate_global_rows():
    rows = [{"original": "全域"}, {"original": "明示全域", "scope": "all"},
            {"original": "別情境", "scope": "cosplay"}]
    assert active_user_terms({"glossary_list": rows}, "all") == rows[:2]


def test_hotwords_only_use_user_rows_and_skip_separators():
    terminology = {"glossary_list": [
        {"original": "全域"}, {"original": "情境", "scope": "cosplay"},
        *({"original": f"前{separator}後"} for separator in (",", "，", "、")),
    ]}
    assert glossary_hotwords(terminology, "cosplay") == ["情境", "全域"]


@pytest.mark.parametrize('typed', ['手打ち, ，、  ', '手打ち、', '手打ち，'])
def test_prompt_strips_trailing_separators(tmp_path, typed):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._coerce_transcription_backend = lambda requested, capabilities: requested
    config = _config(manager, "faster-whisper")
    config["transcription"]["transcription_initial_prompt"] = typed
    assert manager.to_main_args(config)["transcription_initial_prompt"] == "手打ち, リハさん"


@pytest.mark.parametrize('length, expected_words', [(294, True), (295, False), (300, False), (301, False)])
def test_combined_prompt_budget(tmp_path, length, expected_words):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._coerce_transcription_backend = lambda requested, capabilities: requested
    config = _config(manager, "faster-whisper")
    typed = "字" * length
    config["transcription"]["transcription_initial_prompt"] = typed
    prompt = manager.to_main_args(config)["transcription_initial_prompt"]
    assert prompt == typed + (", リハさん" if expected_words else "")
    assert len(prompt) <= max(300, length)


def test_legacy_glossary_keys_follow_scoped_rows(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._coerce_transcription_backend = lambda requested, capabilities: requested
    config = _config(manager, "faster-whisper", terminology_glossary={"旧辞書": "舊字典", "リハさん": "Riha"})
    config["terminology"]["glossary_list"].append({"original": "非使用全域", "scope": "all"})
    assert manager.to_main_args(config)["transcription_initial_prompt"] == "手打ち, リハさん, 旧辞書"


def test_asr_prompt_feed_is_opt_in(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager._coerce_transcription_backend = lambda requested, capabilities: requested
    assert manager.get_config()["terminology"]["glossary_to_asr_prompt"] is False
    config = _config(manager, "faster-whisper")
    del config["terminology"]["glossary_to_asr_prompt"]
    # Whisper can echo prompt words as subtitles on BGM or silence.
    assert manager.to_main_args(config)["transcription_initial_prompt"] == "手打ち"


def test_alias_inside_another_original_is_not_a_correction():
    terminology = {"glossary_list": [
        {"original": "兎田ぺこら", "translated": "Pekora", "aliases": ["ぺこらちゃん"]},
        {"original": "ぺこちゃん", "translated": "x", "aliases": ["ぺこら", "ペコ"]},
    ]}
    rules = glossary_asr_rules(terminology, "")
    assert {"canonical": "ぺこちゃん", "aliases": ["ペコ"]} in rules
    assert all("ぺこら" not in rule["aliases"] for rule in rules)


def test_builtin_asr_variants_apply_without_user_glossary(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = _config(manager, "qwen3-asr", use_terminology_glossary=False)
    config["translation"]["translation_glossary_scope"] = "general_chat"
    rules = json.loads(manager.to_main_args(config)["asr_correction_rules"])
    assert {"canonical": "ノンデリ", "aliases": ["のんでり"]} in rules
    # The user's own aliases stay off with 我的詞條.
    assert all(rule["canonical"] != "リハさん" for rule in rules)


def test_new_installs_ship_general_livestream_terms(tmp_path):
    import shutil
    from pathlib import Path
    example = Path(__file__).resolve().parents[2] / "config.example.yaml"
    shutil.copy(example, tmp_path / "config.yaml")
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    assert config["translation"]["translation_glossary_scope"] == "general_chat"
    assert config["transcription"]["asr_corrections_enabled"] is True
    args = manager.to_main_args(config)
    rules = json.loads(args["asr_correction_rules"])
    assert {"canonical": "ノンデリ", "aliases": ["のんでり"]} in rules
    # 面言 would rewrite 当面言わない; it must not ship as a built-in variant.
    assert all("面言" not in rule["aliases"] for rule in rules)
