from backend.core.language_identity import same_language


def test_same_language_accepts_common_aliases():
    assert same_language("zh-TW", "Traditional Chinese") is True
    assert same_language("ja-JP", "Japanese") is True
    assert same_language("en-US", "English") is True


def test_auto_and_distinct_chinese_scripts_still_translate():
    assert same_language("auto", "Traditional Chinese") is False
    assert same_language("Simplified Chinese", "Traditional Chinese") is False
