from backend.core.config_manager import ConfigManager
from backend.core.runtime_profiles import get_runtime_capabilities


def _config_for(profile: str) -> dict:
    return {
        "runtime": {
            "profile": profile,
            "device_policy": "auto_discrete",
            "allow_integrated_gpu": False,
        },
        "input": {
            "audio_source": "url",
            "url": "",
        },
        "audio_slicing_vad": {},
        "transcription": {
            "backend": "sensevoice",
            "model": "base",
            "language": "auto",
            "use_faster_whisper": False,
            "use_simul_streaming": False,
            "use_openai_transcription_api": False,
            "use_qwen3_asr": False,
            "use_sensevoice_asr": True,
            "sensevoice_model": "iic/SenseVoiceSmall",
        },
        "translation": {
            "backend": "none",
        },
        "output_notification": {},
        "general": {},
    }


def _manager() -> ConfigManager:
    return ConfigManager.__new__(ConfigManager)


def test_sensevoice_is_profile_aware():
    cuda = get_runtime_capabilities("cuda")
    cpu = get_runtime_capabilities("cpu")
    rocm = get_runtime_capabilities("rocm")

    assert "sensevoice" in cuda.local_asr_engines
    assert "sensevoice" in cpu.local_asr_engines
    assert "sensevoice" in rocm.local_asr_engines
    assert cuda.sensevoice_status == "compatibility"
    assert cpu.sensevoice_status == "compatibility"
    assert rocm.sensevoice_status == "experimental"
    assert cuda.sensevoice_model_ids == ("iic/SenseVoiceSmall",)


def test_parakeet_ctc_ja_is_cuda_only():
    cuda = get_runtime_capabilities("cuda")
    cpu = get_runtime_capabilities("cpu")
    rocm = get_runtime_capabilities("rocm")

    assert "parakeet-ctc-ja" in cuda.local_asr_engines
    assert "parakeet-ctc-ja" not in cpu.local_asr_engines
    assert "parakeet-ctc-ja" not in rocm.local_asr_engines
    assert cuda.parakeet_status == "experimental"
    assert cpu.parakeet_status == "disabled"
    assert rocm.parakeet_status == "disabled"
    assert cuda.parakeet_model_ids == ("grider-transwithai/parakeet-ctc-1.1b-ja",)


def test_sensevoice_config_maps_to_cli_args_for_cuda():
    args = _manager().to_main_args(_config_for("cuda"))

    assert args["model"] == "iic/SenseVoiceSmall"
    assert args["use_sensevoice_asr"] is True
    assert args["use_qwen3_asr"] is False
    assert args["sensevoice_model"] == "iic/SenseVoiceSmall"
    assert args["sensevoice_device"] == "auto"
    assert args["preload_asr_model"] is True
    assert args["keep_asr_loaded"] is True


def test_parakeet_ctc_ja_config_maps_to_cli_args_for_cuda():
    config = _config_for("cuda")
    config["transcription"].update({
        "backend": "parakeet-ctc-ja",
        "use_sensevoice_asr": False,
        "use_nemo_asr": True,
        "nemo_asr_model": "grider-transwithai/parakeet-ctc-1.1b-ja",
        "nemo_asr_dtype": "bfloat16",
        "language": "ja",
    })

    args = _manager().to_main_args(config)

    assert args["model"] == "grider-transwithai/parakeet-ctc-1.1b-ja"
    assert args["use_nemo_asr"] is True
    assert args["use_qwen3_asr"] is False
    assert args["use_sensevoice_asr"] is False
    assert args["nemo_asr_model"] == "grider-transwithai/parakeet-ctc-1.1b-ja"
    assert args["nemo_asr_device"] == "auto"
    assert args["nemo_asr_decoding"] == "ctc"
    assert args["nemo_asr_dtype"] == "bfloat16"
    assert args["preload_asr_model"] is True
    assert args["keep_asr_loaded"] is True


def test_parakeet_ctc_ja_falls_back_outside_cuda_profile():
    config = _config_for("cpu")
    config["transcription"].update({
        "backend": "parakeet-ctc-ja",
        "use_sensevoice_asr": False,
        "use_nemo_asr": True,
        "nemo_asr_model": "grider-transwithai/parakeet-ctc-1.1b-ja",
    })

    args = _manager().to_main_args(config)

    assert args["use_nemo_asr"] is False
    assert args["use_qwen3_asr"] is True


def test_sensevoice_model_id_overrides_stale_backend():
    config = _config_for("cuda")
    config["transcription"].update({
        "backend": "faster-whisper",
        "model": "iic/SenseVoiceSmall",
        "use_sensevoice_asr": False,
    })

    args = _manager().to_main_args(config)

    assert args["model"] == "iic/SenseVoiceSmall"
    assert args["use_sensevoice_asr"] is True
    assert args["use_faster_whisper"] is False


def test_sensevoice_config_forces_cpu_device_on_cpu_profile():
    args = _manager().to_main_args(_config_for("cpu"))

    assert args["use_sensevoice_asr"] is True
    assert args["sensevoice_device"] == "cpu"


def test_unsupported_faster_whisper_still_falls_back_to_qwen_on_rocm():
    config = _config_for("rocm")
    config["transcription"].update({
        "backend": "faster-whisper",
        "use_faster_whisper": True,
        "use_sensevoice_asr": False,
    })

    args = _manager().to_main_args(config)

    assert args["use_qwen3_asr"] is True
    assert args["use_sensevoice_asr"] is False
