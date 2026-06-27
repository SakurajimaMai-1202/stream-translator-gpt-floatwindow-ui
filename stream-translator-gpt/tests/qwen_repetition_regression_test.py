import sys

import numpy as np

from stream_translator_gpt.asr_preload import (
    PreloadedTranscriberManager,
    build_asr_config,
    resolve_preload_config,
    resolve_qwen3_preload_runtime_options,
)
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


class _FakeProps:
    def __init__(self, total_memory, arch=None):
        self.total_memory = total_memory
        self.gcnArchName = arch


class _FakeCuda:
    def __init__(self, devices):
        self.devices = devices

    def device_count(self):
        return len(self.devices)

    def get_device_name(self, index):
        return self.devices[index]["name"]

    def get_device_properties(self, index):
        return _FakeProps(self.devices[index].get("memory", 0), self.devices[index].get("arch"))

    def get_arch_list(self):
        arches = []
        for device in self.devices:
            arches.extend(device.get("supported_arches", []))
        return arches


class _FakeTorch:
    def __init__(self, devices):
        self.cuda = _FakeCuda(devices)


class _DummyTranscriber:
    def __init__(self):
        self.prepared = False

    def prepare_for_reuse(self):
        self.prepared = True


def test_preloaded_qwen_rocm_unsupported_gfx_falls_back_to_cpu_float32():
    config = build_asr_config({
        "use_qwen3_asr": True,
        "qwen3_asr_model": "Qwen/Qwen3-ASR-1.7B",
        "qwen3_dtype": "bfloat16",
        "qwen3_asr_device_map": "auto",
        "runtime_profile": "rocm",
        "runtime_device_policy": "auto_discrete",
    })
    torch = _FakeTorch([
        {
            "name": "AMD Radeon RX 9070 XT",
            "memory": 16 * 1024 * 1024 * 1024,
            "arch": "gfx1201",
            "supported_arches": ["gfx1100"],
        },
    ])

    device_map, dtype = resolve_qwen3_preload_runtime_options(torch, config)

    assert device_map == "cpu"
    assert dtype == "float32"


def test_preloaded_manager_resolves_auto_config_before_matching(monkeypatch):
    config = build_asr_config({
        "use_qwen3_asr": True,
        "qwen3_asr_model": "Qwen/Qwen3-ASR-1.7B",
        "qwen3_dtype": "bfloat16",
        "qwen3_asr_device_map": "auto",
        "runtime_profile": "rocm",
        "runtime_device_policy": "auto_discrete",
    })
    fake_torch = _FakeTorch([
        {
            "name": "AMD Radeon RX 7900 XTX",
            "memory": 24 * 1024 * 1024 * 1024,
            "arch": "gfx1100",
            "supported_arches": ["gfx1100"],
        },
    ])
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    manager = PreloadedTranscriberManager()
    transcriber = _DummyTranscriber()
    manager.transcriber = transcriber
    manager.config = resolve_preload_config(config)
    manager.status = "loaded"

    assert manager.get_for_run(config) is transcriber
    assert transcriber.prepared is True
    manager.release()


def test_qwen_duplicate_comparison_ignores_spacing_and_punctuation():
    assert _is_consecutive_duplicate(
        "これはテストです。",
        " これは、テストです ",
    )
    assert not _is_consecutive_duplicate("はい。", "はい。")


def test_pathological_repetition_is_collapsed_to_one_copy():
    assert repetition_filter("同じ文章。同じ文章。同じ文章。同じ文章。") == "同じ文章。"
