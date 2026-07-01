import pytest


pytest.importorskip("scipy")
pytest.importorskip("torch")

from stream_translator_gpt.asr_preload import build_asr_config, resolve_preload_config
from stream_translator_gpt.audio_transcriber import NemoASRTranscriber


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


def test_build_asr_config_selects_sensevoice_backend():
    config = build_asr_config({
        "use_sensevoice_asr": True,
        "sensevoice_model": "iic/SenseVoiceSmall",
        "sensevoice_device": "auto",
        "language": "zh-tw",
    })

    assert config.backend == "sensevoice"
    assert config.model is None
    assert config.sensevoice_model == "iic/SenseVoiceSmall"
    assert config.sensevoice_device == "auto"
    assert "sensevoice" in config.label()


def test_sensevoice_preload_resolves_cpu_profile(monkeypatch):
    fake_torch = _FakeTorch([
        {"name": "NVIDIA GeForce RTX 4070", "memory": 12 * 1024 * 1024 * 1024},
    ])
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    config = build_asr_config({
        "use_sensevoice_asr": True,
        "sensevoice_model": "iic/SenseVoiceSmall",
        "sensevoice_device": "auto",
        "runtime_profile": "cpu",
    })

    resolved = resolve_preload_config(config)

    assert resolved.sensevoice_device == "cpu"


def test_sensevoice_preload_skips_unsupported_rocm_igpu(monkeypatch):
    fake_torch = _FakeTorch([
        {
            "name": "AMD Radeon(TM) Graphics",
            "memory": 2 * 1024 * 1024 * 1024,
            "arch": "gfx1036",
            "supported_arches": ["gfx1036", "gfx1201"],
        },
        {
            "name": "AMD Radeon RX 9070 XT",
            "memory": 16 * 1024 * 1024 * 1024,
            "arch": "gfx1201",
            "supported_arches": ["gfx1036", "gfx1201"],
        },
    ])
    monkeypatch.setitem(__import__("sys").modules, "torch", fake_torch)
    config = build_asr_config({
        "use_sensevoice_asr": True,
        "sensevoice_model": "iic/SenseVoiceSmall",
        "sensevoice_device": "auto",
        "runtime_profile": "rocm",
        "runtime_device_policy": "auto_discrete",
    })

    resolved = resolve_preload_config(config)

    assert resolved.sensevoice_device == "cuda:1"


def test_parakeet_ctc_ja_uses_hf_nemo_file(tmp_path):
    local_model = tmp_path / "parakeet-ja.nemo"
    local_model.write_bytes(b"fake nemo")

    assert NemoASRTranscriber.DEFAULT_MODEL == "grider-transwithai/parakeet-ctc-1.1b-ja"
    assert NemoASRTranscriber.DEFAULT_HF_FILENAME == "parakeet-ja.nemo"
    assert NemoASRTranscriber._resolve_nemo_model_path(str(local_model)) == local_model


def test_parakeet_ctc_ja_dtype_prefers_bfloat16_when_supported():
    class _Cuda:
        @staticmethod
        def is_bf16_supported():
            return True

    class _Torch:
        cuda = _Cuda()
        bfloat16 = "bf16"
        float16 = "fp16"

    assert NemoASRTranscriber._resolve_dtype(_Torch, "bfloat16", "cuda:0") == ("bfloat16", "bf16")
    assert NemoASRTranscriber._resolve_dtype(_Torch, "auto", "cuda:0") == ("bfloat16", "bf16")


def test_parakeet_ctc_ja_dtype_falls_back_to_float16_without_bfloat16():
    class _Cuda:
        @staticmethod
        def is_bf16_supported():
            return False

    class _Torch:
        cuda = _Cuda()
        bfloat16 = "bf16"
        float16 = "fp16"

    assert NemoASRTranscriber._resolve_dtype(_Torch, "bfloat16", "cuda:0") == ("float16", "fp16")
    assert NemoASRTranscriber._resolve_dtype(_Torch, "float32", "cuda:0") == ("float32", None)
