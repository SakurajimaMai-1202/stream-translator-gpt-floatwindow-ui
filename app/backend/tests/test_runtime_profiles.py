from backend.core.runtime_profiles import default_runtime_config, get_runtime_capabilities, normalize_runtime_profile


def test_gpu_profiles_default_qwen3_to_bfloat16():
    assert get_runtime_capabilities("cuda").qwen3_default_dtype == "bfloat16"
    assert get_runtime_capabilities("rocm").qwen3_default_dtype == "bfloat16"


def test_cpu_profile_defaults_qwen3_to_float32():
    capabilities = get_runtime_capabilities("cpu")

    assert capabilities.qwen3_default_dtype == "float32"
    assert capabilities.default_device_policy == "cpu"
    assert not capabilities.faster_whisper_gpu_enabled


def test_rocm_profile_keeps_faster_whisper_disabled():
    capabilities = get_runtime_capabilities("rocm")

    assert capabilities.status == "experimental"
    assert capabilities.faster_whisper_status == "disabled"
    assert capabilities.faster_whisper_cpu_fallback


def test_unknown_profile_falls_back_to_cuda():
    assert normalize_runtime_profile("something-new") == "cuda"
    assert default_runtime_config("something-new")["profile"] == "cuda"
