import asyncio
import copy
import json

import pytest
import yaml

from backend.core.config_manager import ConfigManager
from backend.core.hy_mt2_glossary_presets import (
    PRESETS, PRESET_ASR_VARIANTS, session_vocabulary,
)


@pytest.mark.parametrize("scope,preset,expected", [
    ("cosplay", "hololive_vtuber", ["general_chat", "cosplay"]),
    (None, "hololive_vtuber", ["general_chat", "hololive_vtuber"]),
    ("all", "general_chat", []),
    ("", "hololive_vtuber", []),
    ("hololive_vtuber", "", ["general_chat", "hololive_vtuber"]),
    (None, "", []),
    (None, "all", []),
])
@pytest.mark.parametrize("route", ["load", "import"])
def test_migration_load_and_import(tmp_path, scope, preset, expected, route):
    legacy = {
        "translation": {"translation_glossary_scope": scope, "hy_mt2_glossary_preset": preset},
        "terminology": {"use_terminology_glossary": False, "glossary_list": [
            {"original": "Existing", "translated": "Scoped", "scope": "cosplay", "aliases": []},
            {"original": "Existing", "translated": "Global", "scope": "all", "aliases": "old, duplicate"},
            {"original": "ScopedOnly", "translated": "First", "scope": "cosplay"},
            {"original": "ScopedOnly", "translated": "Second", "scope": "hololive_vtuber"},
        ], "terminology_glossary": {"Existing": "Override", "Legacy": "Translation"}},
        "transcription": {"asr_correction_rules": [
            {"canonical": "Existing", "aliases": ["duplicate", "new"]},
            {"canonical": "ScopedOnly", "aliases": "variant, variant"},
            {"canonical": "ASROnly", "aliases": ["misheard"]},
        ]},
    }
    path = tmp_path / "config.yaml"
    if route == "load":
        path.write_text(yaml.safe_dump(legacy), encoding="utf-8")
        manager = ConfigManager(path)
    else:
        manager = ConfigManager(path)
        manager.replace_config(legacy)
    config = manager.get_config()
    terminology = config["terminology"]
    assert terminology["schema_version"] == 2
    assert terminology["active_categories"] == expected
    assert terminology["use_terminology_glossary"] is False
    assert config["translation"]["translation_glossary_scope"] == scope
    assert config["transcription"]["asr_correction_rules"] == []
    assert terminology["terminology_glossary"] == {}
    rows = terminology["glossary_list"]
    assert rows[0]["aliases"] == []
    assert rows[1]["aliases"] == ["old", "duplicate", "new"]
    assert rows[1]["translated"] == "Override"
    assert rows[0]["translated"] == "Scoped"
    # A manual rule applied to every session, so without a 一般 row it becomes
    # its own ASR-only 一般 row instead of joining a category row.
    assert rows[2]["aliases"] == []
    assert rows[3]["aliases"] == []
    assert rows[4] == {"original": "ScopedOnly", "translated": "", "aliases": ["variant"], "scope": "all"}
    assert rows[5] == {"original": "ASROnly", "translated": "", "aliases": ["misheard"], "scope": "all"}
    assert rows[6] == {"original": "Legacy", "translated": "Translation", "aliases": [], "scope": "all"}
    snapshot = copy.deepcopy(config)
    again, changed = manager._migrate_legacy_config(config)
    assert changed is False
    assert again == snapshot
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert saved["terminology"] == terminology


def test_migration_preserves_explicit_categories_and_reports_changes(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["terminology"].pop("schema_version")
    config["translation"]["translation_glossary_scope"] = "cosplay"
    migrated, changed = manager._migrate_legacy_config(config)
    assert changed is True
    assert migrated["terminology"]["active_categories"] == []
    assert manager._migrate_legacy_config(migrated)[1] is False


def vocabulary(**terminology):
    return session_vocabulary({"terminology": {
        "schema_version": 2, "use_terminology_glossary": True,
        "active_categories": ["general_chat", "hololive_vtuber"], **terminology,
    }, "translation": {"translation_glossary_scope": "cosplay", "hy_mt2_glossary_preset": "cosplay"}})


def test_multiple_categories_and_global_rows():
    result = vocabulary(glossary_list=[
        {"original": "Global", "translated": "G", "scope": "all"},
        {"original": "Private", "translated": "P", "scope": "custom_x"},
    ])
    assert result["active_categories"] == {"all", "general_chat", "hololive_vtuber"}
    assert result["translation_terms"]["マシュマロ"] == "棉花糖"
    assert result["translation_terms"]["ホロライブ"] == "Hololive"
    assert result["translation_terms"]["Global"] == "G"
    assert "Private" not in result["translation_terms"]
    assert "ウィッグ" not in result["translation_terms"]


def test_disabled_builtin_removes_canonical_and_variants():
    result = vocabulary(builtin_disabled=[{"category": "general_chat", "source": "マシュマロ"}])
    assert not {"マシュマロ", "マシュモロ", "マシモロ"} & result["translation_terms"].keys()
    assert all(rule["canonical"] != "マシュマロ" for rule in result["asr_rules"])
    # Disabling a term in another category has no effect.
    assert "マシュマロ" in vocabulary(builtin_disabled=[{"category": "cosplay", "source": "マシュマロ"}])["translation_terms"]


def test_user_overrides_and_asr_only_rows():
    result = vocabulary(glossary_list=[
        {"original": "ホロライブ", "translated": "Mine", "aliases": "Holo, Holo"},
        {"original": "Correct", "translated": "", "aliases": ["Wrong"]},
    ])
    assert result["translation_terms"]["ホロライブ"] == "Mine"
    assert result["translation_terms"]["Holo"] == "Mine"
    assert "Correct" not in result["translation_terms"] and "Wrong" not in result["translation_terms"]
    assert {"canonical": "Correct", "aliases": ["Wrong"]} in result["asr_rules"]


def test_user_switch_keeps_builtins():
    result = vocabulary(use_terminology_glossary=False, glossary_list=[
        {"original": "Private", "translated": "P", "aliases": ["Wrong"]},
    ])
    assert "Private" not in result["translation_terms"]
    assert "マシュマロ" in result["translation_terms"]
    assert result["hotwords"] == []
    assert {"canonical": "Private", "aliases": ["Wrong"]} in result["asr_rules"]
    assert any(rule["canonical"] == "マシュマロ" for rule in result["asr_rules"])


def test_safety_filter_includes_builtin_and_user_originals():
    result = vocabulary(glossary_list=[
        {"original": "Correct", "aliases": ["ホロ", "Safe"]},
        {"original": "のんでりさん", "translated": "Name"},
    ])
    assert {"canonical": "Correct", "aliases": ["Safe"]} in result["asr_rules"]
    assert all("のんでり" not in rule["aliases"] for rule in result["asr_rules"])
    assert all("面言" not in rule["aliases"] for rule in result["asr_rules"])


def test_api_categories_are_ordered_and_independent():
    from backend.api.config import get_hy_mt2_glossary_presets
    result = asyncio.run(get_hy_mt2_glossary_presets())
    assert list(result) == ["categories"]
    assert [row["id"] for row in result["categories"]] == ["general_chat", "hololive_vtuber", "cosplay"]
    assert [row["label"] for row in result["categories"]] == ["一般直播", "Hololive／VTuber", "Cosplay"]
    seen = set()
    for category in result["categories"]:
        name = category["id"]
        assert set(category) == {"id", "label", "terms", "asr_variants"}
        assert category["terms"] == PRESETS[name]
        assert category["asr_variants"] == PRESET_ASR_VARIANTS[name]
        assert not seen.intersection(category["terms"])
        seen.update(category["terms"])
    result["categories"][0]["asr_variants"]["マシュマロ"].append("mutation")
    assert "mutation" not in PRESET_ASR_VARIANTS["general_chat"]["マシュマロ"]


@pytest.mark.parametrize("family", ["hy_mt2", "index_translate"])
@pytest.mark.parametrize("smart", [True, False])
def test_engine_feeds_share_vocabulary(tmp_path, family, smart):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["translation"].update({"backend": "gpt", "translation_model_family": family,
                                  "use_smart_prompt": smart})
    config["terminology"].update({"active_categories": ["general_chat", "cosplay"],
        "glossary_list": [{"original": "Private", "translated": "P", "aliases": ["Wrong"]}]})
    expected = session_vocabulary(config)
    args = manager.to_main_args(config)
    assert json.loads(args["translation_glossary"]) == expected["translation_terms"]
    assert json.loads(args[f"{family}_aliases"]) == expected["translation_terms"]
    assert json.loads(args["asr_correction_rules"]) == expected["asr_rules"]


@pytest.mark.parametrize("rows", [None, "invalid", {}])
def test_legacy_dict_with_invalid_glossary_list(tmp_path, rows):
    # Loading rejects these shapes before migration; the migration itself must
    # still not crash if it is ever handed one.
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager._merge_with_defaults({})
    config["terminology"].pop("schema_version", None)
    config["terminology"].update({"glossary_list": rows, "terminology_glossary": {"Legacy": "Target"}})
    config, _ = manager._migrate_legacy_config(config)
    assert config["terminology"]["glossary_list"] == [
        {"original": "Legacy", "translated": "Target", "aliases": [], "scope": "all"},
    ]
    assert config["terminology"]["terminology_glossary"] == {}
    assert manager._migrate_legacy_config(config)[1] is False


@pytest.mark.parametrize("enabled", [True, False])
def test_user_glossary_switch_does_not_gate_asr_args(tmp_path, enabled):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = manager.get_config()
    config["terminology"].update({
        "use_terminology_glossary": False, "active_categories": [],
        "glossary_to_asr_prompt": True,
        "glossary_list": [
            {"original": "Correct", "translated": "Translation", "aliases": ["Wrong"]},
            {"original": "ASROnly", "translated": "", "aliases": ["Misheard"]},
        ],
    })
    config["transcription"]["asr_corrections_enabled"] = enabled
    args = manager.to_main_args(config)
    assert args["asr_corrections_enabled"] is enabled
    assert json.loads(args["asr_correction_rules"]) == [
        {"canonical": "Correct", "aliases": ["Wrong"]},
        {"canonical": "ASROnly", "aliases": ["Misheard"]},
    ]
    assert not session_vocabulary(config)["translation_terms"]
    assert not session_vocabulary(config)["hotwords"]
    config["transcription"]["asr_corrections_enabled"] = not enabled
    assert manager.to_main_args(config)["asr_correction_rules"] == args["asr_correction_rules"]


@pytest.mark.parametrize("translated,kept", [("Sui", True), ("Other", False), ("", True)])
def test_alias_safety_for_asr_only_substrings_and_exact_originals(translated, kept):
    result = vocabulary(active_categories=[], glossary_list=[
        {"original": "すいちゃん", "translated": "Sui", "aliases": ["らスイちゃ", "スイちゃん"]},
        {"original": "らスイちゃ", "translated": translated},
        {"original": "スイちゃん", "translated": "Sui"},
        # ASR-only, yet still the correct spelling: 麻衣 must not rewrite it.
        {"original": "桜島麻衣", "translated": ""},
        {"original": "真衣", "aliases": ["麻衣", "真衣", "Safe"]},
    ])
    rules = {row["canonical"]: row["aliases"] for row in result["asr_rules"]}
    # An exact other original may be rewritten only with no or the same meaning.
    assert ("らスイちゃ" in rules["すいちゃん"]) is kept
    assert "スイちゃん" in rules["すいちゃん"]
    assert rules["真衣"] == ["Safe"]


def test_blank_override_in_builtin_category_drops_builtin_translation_only():
    base = [{"original": "マシュマロ", "translated": "", "aliases": [], "scope": "general_chat"}]
    result = vocabulary(active_categories=["general_chat"], glossary_list=base)
    assert "マシュマロ" not in result["translation_terms"]
    assert "マシュモロ" not in result["translation_terms"]
    # The built-in ASR variants still correct recognition.
    assert {"canonical": "マシュマロ", "aliases": ["マシュモロ", "マシモロ"]} in result["asr_rules"]
    # A blank 一般 row (e.g. a migrated ASR rule) is not an override.
    other = vocabulary(active_categories=["general_chat"], glossary_list=[{**base[0], "scope": "all"}])
    assert other["translation_terms"]["マシュマロ"] == "棉花糖"
