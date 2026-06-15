import numpy as np

from stream_translator_gpt.asr_preload import build_asr_config
from stream_translator_gpt.audio_slicer import AudioSlicer
from stream_translator_gpt.audio_transcriber import _is_consecutive_duplicate
from stream_translator_gpt.filters import repetition_filter


def _make_slicer(prefix_retention_length: float) -> AudioSlicer:
    return AudioSlicer(
        min_audio_length=0.1,
        max_audio_length=30.0,
        target_audio_length=5.0,
        continuous_no_speech_threshold=1.0,
        dynamic_no_speech_threshold=False,
        prefix_retention_length=prefix_retention_length,
        vad_threshold=0.35,
        dynamic_vad_threshold=False,
        disable_vad=True,
    )


def test_zero_prefix_retention_does_not_replay_previous_audio():
    slicer = _make_slicer(0)
    slicer.audio_buffer = [np.array([1.0, 2.0], dtype=np.float32)]

    first_audio, _ = slicer.slice()
    assert first_audio.tolist() == [1.0, 2.0]
    assert slicer.prefix_audio_buffer == []

    slicer.audio_buffer = [np.array([3.0], dtype=np.float32)]
    second_audio, _ = slicer.slice()
    assert second_audio.tolist() == [3.0]


def test_preloaded_qwen_uses_ui_dtype_setting():
    config = build_asr_config({
        "use_qwen3_asr": True,
        "qwen3_asr_model": "Qwen/Qwen3-ASR-1.7B",
        "qwen3_dtype": "float32",
    })

    assert config.qwen3_asr_dtype == "float32"


def test_qwen_duplicate_comparison_ignores_spacing_and_punctuation():
    assert _is_consecutive_duplicate(
        "これはテストです。",
        " これは、テストです ",
    )
    assert not _is_consecutive_duplicate("はい。", "はい。")


def test_pathological_repetition_is_collapsed_to_one_copy():
    assert repetition_filter("同じ文章。同じ文章。同じ文章。同じ文章。") == "同じ文章。"
