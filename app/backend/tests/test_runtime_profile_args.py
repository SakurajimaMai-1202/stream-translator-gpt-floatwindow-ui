import copy

from backend.core.config_manager import ConfigManager


def _qwen3_config(profile: str, qwen3_dtype: str = "bfloat16"):
    config = copy.deepcopy(ConfigManager.DEFAULT_CONFIG)
    config["runtime"]["profile"] = profile
    config["transcription"]["backend"] = "qwen3-asr"
    config["transcription"]["qwen3_dtype"] = qwen3_dtype
    return config


def test_cuda_profile_keeps_qwen3_bfloat16_and_auto_device_map(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")

    args = manager.to_main_args(_qwen3_config("cuda"))

    assert args["runtime_profile"] == "cuda"
    assert args["runtime_device_policy"] == "auto_discrete"
    assert args["runtime_allow_integrated_gpu"] is False
    assert args["qwen3_dtype"] == "bfloat16"
    assert args["qwen3_asr_dtype"] == "bfloat16"
    assert args["qwen3_asr_device_map"] == "auto"


def test_rocm_profile_keeps_qwen3_bfloat16_and_auto_device_map(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")

    args = manager.to_main_args(_qwen3_config("rocm"))

    assert args["runtime_profile"] == "rocm"
    assert args["runtime_device_policy"] == "auto_discrete"
    assert args["runtime_allow_integrated_gpu"] is False
    assert args["qwen3_dtype"] == "bfloat16"
    assert args["qwen3_asr_dtype"] == "bfloat16"
    assert args["qwen3_asr_device_map"] == "auto"


def test_cpu_profile_rewrites_default_qwen3_bfloat16_to_float32_cpu(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")

    args = manager.to_main_args(_qwen3_config("cpu"))

    assert args["runtime_profile"] == "cpu"
    assert args["runtime_device_policy"] == "cpu"
    assert args["qwen3_dtype"] == "float32"
    assert args["qwen3_asr_dtype"] == "float32"
    assert args["qwen3_asr_device_map"] == "cpu"


def test_cpu_profile_preserves_explicit_qwen3_float32(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")

    args = manager.to_main_args(_qwen3_config("cpu", qwen3_dtype="float32"))

    assert args["qwen3_dtype"] == "float32"
    assert args["qwen3_asr_dtype"] == "float32"
    assert args["qwen3_asr_device_map"] == "cpu"


def test_runtime_integrated_gpu_override_is_passed_to_asr_runtime(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = _qwen3_config("rocm")
    config["runtime"]["allow_integrated_gpu"] = True

    args = manager.to_main_args(config)

    assert args["runtime_allow_integrated_gpu"] is True
