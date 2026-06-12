from types import SimpleNamespace

from stream_translator_gpt.audio_transcriber import Qwen3ASRTranscriber


class _FakeCuda:
    @staticmethod
    def is_available():
        return True

    @staticmethod
    def get_arch_list():
        return ["gfx1100", "gfx1200"]

    @staticmethod
    def device_count():
        return 1

    @staticmethod
    def get_device_properties(_index):
        return SimpleNamespace(name="AMD Radeon(TM) Graphics", gcnArchName="gfx1036:sramecc+:xnack-")

    @staticmethod
    def get_device_name(_index):
        return "AMD Radeon(TM) Graphics"


class _FakeTorch:
    cuda = _FakeCuda()
    version = SimpleNamespace(hip="6.4")


def test_unsupported_rocm_arch_falls_back_to_cpu():
    assert Qwen3ASRTranscriber._resolve_device_map(_FakeTorch(), "auto") == "cpu"


class _MixedGpuCuda(_FakeCuda):
    @staticmethod
    def get_arch_list():
        return ["gfx1100", "gfx1200", "gfx1201"]

    @staticmethod
    def device_count():
        return 2

    @staticmethod
    def get_device_properties(index):
        if index == 0:
            return SimpleNamespace(name="AMD Radeon(TM) Graphics", gcnArchName="gfx1036")
        return SimpleNamespace(name="AMD Radeon RX 9070 XT", gcnArchName="gfx1201:sramecc+:xnack-")

    @staticmethod
    def get_device_name(index):
        return "AMD Radeon(TM) Graphics" if index == 0 else "AMD Radeon RX 9070 XT"


class _MixedGpuTorch:
    cuda = _MixedGpuCuda()
    version = SimpleNamespace(hip="7.2")


def test_auto_selects_supported_discrete_gpu_after_unsupported_integrated_gpu():
    assert Qwen3ASRTranscriber._resolve_device_map(_MixedGpuTorch(), "auto") == "cuda:1"


def test_explicit_supported_gpu_is_preserved():
    assert Qwen3ASRTranscriber._resolve_device_map(_MixedGpuTorch(), "cuda:1") == "cuda:1"


def test_explicit_unsupported_gpu_falls_back_to_cpu():
    assert Qwen3ASRTranscriber._resolve_device_map(_MixedGpuTorch(), "cuda:0") == "cpu"
