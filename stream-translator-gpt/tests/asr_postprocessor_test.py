import json
import logging

from stream_translator_gpt.asr_postprocessor import (
    ASRTermCorrector,
    configure_asr_correction_logging,
    configure_asr_correction_learning,
    log_asr_correction,
    observe_asr_correction_candidate,
)


def test_corrects_multiple_aliases_to_canonical_name():
    corrector = ASRTermCorrector([
        {
            "canonical": "桜島麻衣",
            "aliases": ["櫻島麻衣", "櫻島舞衣", "桜島舞衣"],
        }
    ])

    assert corrector.apply("櫻島舞衣和櫻島麻衣") == "桜島麻衣和桜島麻衣"


def test_prefers_longest_alias_and_does_not_chain_replacements():
    corrector = ASRTermCorrector([
        {"canonical": "Alpha", "aliases": ["A", "Alpha test"]},
        {"canonical": "Omega", "aliases": ["Alpha"]},
    ], case_sensitive=True)

    assert corrector.apply("Alpha test A") == "Alpha Alpha"


def test_matches_latin_aliases_case_insensitively_by_default():
    corrector = ASRTermCorrector(
        '[{"canonical":"Qwen3-ASR","aliases":["qwen 3 asr"]}]'
    )

    assert corrector.apply("QWEN 3 ASR is ready") == "Qwen3-ASR is ready"


def test_invalid_rules_leave_text_unchanged():
    assert ASRTermCorrector("not-json").apply("桜島麻衣") == "桜島麻衣"


def test_apply_with_details_reports_actual_alias_matches():
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": ["水星さんとこ"]},
    ])

    corrected, matches = corrector.apply_with_details("水星さんとこです")

    assert corrected == "すいせいさんです"
    assert matches == [{"alias": "水星さんとこ", "canonical": "すいせいさん"}]


def test_suggest_aliases_only_returns_conservative_typo_candidates():
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": []},
    ])

    suggestions = corrector.suggest_aliases("すいせいさnです")

    assert suggestions[0]["alias"] == "すいせいさn"
    assert suggestions[0]["canonical"] == "すいせいさん"
    assert suggestions[0]["score"] >= 0.82
    assert corrector.suggest_aliases("水星さんとこ") == []


def test_suggest_aliases_normalizes_katakana_and_uses_known_aliases():
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": ["スイちゃん"]},
    ])

    suggestions = corrector.suggest_aliases("今日はスイちゃが配信します")

    assert suggestions[0]["alias"] == "スイちゃ"
    assert suggestions[0]["canonical"] == "すいせいさん"
    assert suggestions[0]["matched_anchor"] == "スイちゃん"


def test_suggest_aliases_extracts_name_core_instead_of_whole_sentence():
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": []},
    ])

    suggestions = corrector.suggest_aliases("星街すいせいです")

    assert suggestions[0]["alias"] == "すいせい"
    assert suggestions[0]["canonical"] == "すいせいさん"


def test_suggest_aliases_skips_matched_target_but_finds_another_target():
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": ["スイちゃん"]},
        {"canonical": "あぼさん", "aliases": []},
    ])

    suggestions = corrector.suggest_aliases("スイちゃんとあぼさnです")

    assert suggestions == [{
        "alias": "あぼさn",
        "canonical": "あぼさん",
        "score": 0.97,
        "matched_anchor": "あぼさん",
    }]


def test_standalone_correction_log_writes_jsonl(tmp_path):
    log_path = tmp_path / "asr_corrections.log"
    configure_asr_correction_logging(True, log_path)
    try:
        log_asr_correction({
            "event": "correction_applied",
            "raw_transcript": "水星さんとこ",
            "corrected_transcript": "すいせいさん",
        })

        handler = next(iter(logging.getLogger("asr.corrections").handlers))
        handler.flush()
        payload = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert payload["event"] == "correction_applied"
        assert payload["raw_transcript"] == "水星さんとこ"
    finally:
        configure_asr_correction_logging(False)


def test_candidate_learning_writes_counts_and_suggestions(tmp_path):
    candidate_log = tmp_path / "asr_correction_candidates.log"
    summary_path = tmp_path / "asr_correction_suggestions.json"
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": []},
    ])
    configure_asr_correction_learning(True, candidate_log, summary_path)
    try:
        observe_asr_correction_candidate(corrector, "すいせいさnです", segment_id=7)
        observe_asr_correction_candidate(corrector, "すいせいさnです", segment_id=8)

        handler = next(iter(logging.getLogger("asr.correction_candidates").handlers))
        handler.flush()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["version"] == 2
        assert summary["records"][0]["count"] == 2
        assert summary["records"][0]["canonical"] == "すいせいさん"
        assert summary["records"][0]["alias"] == "すいせいさn"
        assert summary["records"][0]["examples"] == ["すいせいさnです"]
        assert summary["pending_records"] == []
        assert len(candidate_log.read_text(encoding="utf-8").splitlines()) == 2
    finally:
        configure_asr_correction_learning(False)


def test_candidate_learning_keeps_one_off_alias_pending_and_ignores_punctuation(tmp_path):
    candidate_log = tmp_path / "asr_correction_candidates.log"
    summary_path = tmp_path / "asr_correction_suggestions.json"
    corrector = ASRTermCorrector([
        {"canonical": "すいせいさん", "aliases": []},
    ])
    configure_asr_correction_learning(True, candidate_log, summary_path)
    try:
        observe_asr_correction_candidate(corrector, "。")
        observe_asr_correction_candidate(corrector, "星街すいせいです")

        handler = next(iter(logging.getLogger("asr.correction_candidates").handlers))
        handler.flush()
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["records"] == []
        assert summary["pending_records"][0]["alias"] == "すいせい"
        assert len(candidate_log.read_text(encoding="utf-8").splitlines()) == 1
    finally:
        configure_asr_correction_learning(False)
