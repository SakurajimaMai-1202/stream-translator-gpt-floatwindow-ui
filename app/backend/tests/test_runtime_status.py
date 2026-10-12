import copy

from backend.core.config_manager import ConfigManager
from backend.core.hardware_detector import GpuDevice
from backend.core.runtime_status import build_runtime_status


def _config(profile: str, **runtime_overrides):
    config = copy.deepcopy(ConfigManager.DEFAULT_CONFIG)
    config["runtime"]["profile"] = profile
    config["runtime"].update(runtime_overrides)
    return config


def test_runtime_status_selects_cuda_discrete_gpu():
    status = build_runtime_status(
        _config("cuda"),
        devices=[
            GpuDevice(0, "Intel Iris Xe Graphics", "intel", "unknown", 1024, True),
            GpuDevice(1, "NVIDIA GeForce RTX 4070", "nvidia", "cuda", 8192, False),
        ],
    )

    assert status["profile"] == "cuda"
    assert status["capabilities"]["qwen3_default_dtype"] == "bfloat16"
    assert status["selection"]["kind"] == "gpu"
    assert status["selection"]["device"]["index"] == 1
    assert [device["index"] for device in status["selection"]["ignored_devices"]] == [0]


def test_runtime_status_rocm_skips_integrated_gpu_by_default():
    status = build_runtime_status(
        _config("rocm"),
        devices=[
            GpuDevice(0, "AMD Radeon(TM) Graphics", "amd", "rocm", 2048, True, is_supported_by_torch=True),
            GpuDevice(1, "AMD Radeon RX 7900 XTX", "amd", "rocm", 24576, False, is_supported_by_torch=True),
        ],
    )

    assert status["profile"] == "rocm"
    assert status["status"] == "experimental"
    assert status["capabilities"]["faster_whisper_status"] == "disabled"
    assert status["selection"]["kind"] == "gpu"
    assert status["selection"]["device"]["index"] == 1
    assert [device["index"] for device in status["selection"]["ignored_devices"]] == [0]


def test_runtime_status_rocm_allows_integrated_when_enabled():
    status = build_runtime_status(
        _config("rocm", allow_integrated_gpu=True),
        devices=[
            GpuDevice(0, "AMD Radeon(TM) Graphics", "amd", "rocm", 2048, True, is_supported_by_torch=True),
        ],
    )

    assert status["allow_integrated_gpu"] is True
    assert status["selection"]["kind"] == "gpu"
    assert status["selection"]["device"]["index"] == 0


def test_runtime_status_rocm_ignores_unsupported_gfx_arch():
    status = build_runtime_status(
        _config("rocm"),
        devices=[
            GpuDevice(
                0,
                "AMD Radeon RX 9070 XT",
                "amd",
                "rocm",
                16384,
                False,
                arch_name="gfx1201",
                is_supported_by_torch=False,
            ),
        ],
    )

    assert status["selection"]["kind"] == "none"
    assert status["selection"]["device"] is None
    assert status["selection"]["ignored_devices"][0]["arch_name"] == "gfx1201"
    assert status["selection"]["ignored_devices"][0]["is_supported_by_torch"] is False


def test_runtime_status_cpu_forces_cpu_policy():
    status = build_runtime_status(
        _config("cpu", device_policy="auto_discrete"),
        devices=[
            GpuDevice(0, "NVIDIA GeForce RTX 4070", "nvidia", "cuda", 8192, False),
        ],
    )

    assert status["profile"] == "cpu"
    assert status["device_policy"] == "cpu"
    assert status["capabilities"]["qwen3_default_dtype"] == "float32"
    assert status["selection"]["kind"] == "cpu"
    assert status["selection"]["device"] is None
