import json

import pytest

from backend.core.config_manager import ConfigManager
from backend.core.hy_mt2_glossary_presets import glossary_asr_rules, glossary_hotwords


def _config(manager, backend, **terminology):
    config = manager.get_config()
    flags = {"use_qwen3_asr": "qwen3-asr", "use_faster_whisper": "faster-whisper",
             "use_sensevoice_asr": "sensevoice", "use_nemo_asr": "parakeet-ctc-ja"}
    config["transcription"].update({flag: name == backend for flag, name in flags.items()})
    config["transcription"].update({"backend": backend, "transcription_initial_prompt": "手打ち",
                                    "asr_correction_rules": [{"canonical": "すいちゃん", "aliases": ["スイちゃん", "らスイちゃ"]}]})
    config["translation"]["translation_glossary_scope"] = "cosplay"
    config["terminology"].update({"use_terminology_glossary": True, "glossary_list": [
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
        assert "マシュマロ" in words and "マシモロ" not in words
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
