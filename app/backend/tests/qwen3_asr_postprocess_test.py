from stream_translator_gpt.qwen3_asr_postprocess import (
    normalize_chinese_script,
    strip_qwen3_asr_markers,
)


def test_strip_qwen3_asr_markers_preserves_recognized_text():
    assert strip_qwen3_asr_markers("language Japanese:\n<asr_text>こんにちは</asr_text>") == "こんにちは"
    assert strip_qwen3_asr_markers("<|im_start|><asr_text>Hello<|im_end|></asr_text>") == "Hello"


def test_normalize_chinese_script_uses_requested_variant():
    assert normalize_chinese_script("软件里面", "zh-TW") == "軟體裡面"
    assert normalize_chinese_script("軟體裡面", "zh-CN") == "软体里面"
    assert normalize_chinese_script("軟體裡面", "ja") == "軟體裡面"
