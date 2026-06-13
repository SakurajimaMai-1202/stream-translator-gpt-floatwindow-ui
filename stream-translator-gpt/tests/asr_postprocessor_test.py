from stream_translator_gpt.asr_postprocessor import ASRTermCorrector


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
