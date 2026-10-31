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


def test_haas_cpu_sidecar_language_and_gpu_fallback(tmp_path):
    from backend.core.runtime_profiles import get_asr_capabilities
    from backend.core.asr_model_capabilities import coerce_model_language
    model = "oboroge0/Haas-ja-v1.0-onnx-quantized"
    manager = ConfigManager(tmp_path / "config.yaml")
    assert coerce_model_language(model, "en") == "ja"
    for profile in ("cpu", "cuda", "rocm"):
        assert get_asr_capabilities(profile, "cpu").parakeet_model_ids[-1] == model
        config = _qwen3_config(profile)
        config["transcription"].update(backend="parakeet-ctc-ja", asr_compute_backend="cpu",
                                       nemo_asr_model=model, language="en",
                                       use_qwen3_asr=False, use_nemo_asr=True)
        args = manager.to_main_args(config)
        assert args["use_nemo_asr"]
        assert args["model"] == args["nemo_asr_model"] == model
        assert args["language"] == "ja"
        if profile != "cpu":
            assert model not in get_asr_capabilities(profile, "gpu").parakeet_model_ids
            config["transcription"]["asr_compute_backend"] = "gpu"
            args = manager.to_main_args(config)
            assert args["model"] != model
            if profile == "cuda":
                assert args["nemo_asr_model"] == "nvidia/parakeet-tdt_ctc-0.6b-ja"



def test_haas_leftover_model_does_not_override_cpu_parakeet_selection(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    config = _qwen3_config("cpu")
    config["transcription"].update(
        backend="parakeet-ctc-ja", asr_compute_backend="cpu",
        model="oboroge0/Haas-ja-v1.0-onnx-quantized",
        nemo_asr_model="nvidia/parakeet-tdt-0.6b-v3",
        use_qwen3_asr=False, use_nemo_asr=True,
    )
    args = manager.to_main_args(config)
    assert args["model"] == args["nemo_asr_model"] == "nvidia/parakeet-tdt-0.6b-v3"
