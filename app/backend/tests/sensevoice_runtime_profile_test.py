from backend.core.config_manager import ConfigManager
from backend.core.runtime_profiles import get_asr_capabilities, get_runtime_capabilities
from backend.core.runtime_status import build_runtime_status
from backend.core.asr_model_capabilities import (
    coerce_model_language,
    list_asr_model_capabilities,
)


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


def test_packaged_cpu_profile_is_locked_in_config_and_status(monkeypatch, tmp_path):
    monkeypatch.setenv("STREAM_TRANSLATOR_PACKAGED_PROFILE", "cpu")
    config_path = tmp_path / "config.yaml"
    config_path.write_text("runtime:\n  profile: cuda\n  device_policy: auto_discrete\n", encoding="utf-8")

    manager = ConfigManager(config_path)
    assert manager.get_config()["runtime"]["profile"] == "cpu"
    updated = manager.update_config({"runtime": {"profile": "rocm", "device_policy": "auto_any"}})
    assert updated["runtime"]["profile"] == "cpu"
    assert updated["runtime"]["device_policy"] == "cpu"
    assert updated["transcription"]["asr_compute_backend"] == "cpu"

    status = build_runtime_status(updated, devices=[])
    assert status["profile_locked"] is True
    assert status["packaged_profile"] == "cpu"
    assert status["profile"] == "cpu"
    assert status["effective_asr_compute_backend"] == "cpu"


def test_cuda_package_can_select_cpu_sherpa_capabilities(monkeypatch):
    monkeypatch.setenv("STREAM_TRANSLATOR_PACKAGED_PROFILE", "cuda")
    config = _config_for("cuda")
    config["transcription"].update({
        "asr_compute_backend": "cpu",
        "backend": "parakeet-ctc-ja",
        "use_sensevoice_asr": False,
        "use_nemo_asr": True,
        "nemo_asr_model": "nvidia/parakeet-tdt-0.6b-v3",
    })

    args = _manager().to_main_args(config)
    status = build_runtime_status(config, devices=[])

    assert args["runtime_profile"] == "cuda"
    assert args["asr_compute_backend"] == "cpu"
    assert args["model"] == "nvidia/parakeet-tdt-0.6b-v3"
    assert status["profile"] == "cuda"
    assert status["effective_asr_compute_backend"] == "cpu"
    assert status["asr_capabilities"]["profile"] == "cpu"
    assert "nvidia/parakeet-tdt-0.6b-v3" in status["asr_capabilities"]["parakeet_model_ids"]
    assert get_asr_capabilities("rocm", "cpu").profile == "cpu"


def test_sensevoice_is_profile_aware():
    cuda = get_runtime_capabilities("cuda")
    cpu = get_runtime_capabilities("cpu")
    rocm = get_runtime_capabilities("rocm")

    assert "sensevoice" in cuda.local_asr_engines
    assert "sensevoice" in cpu.local_asr_engines
    assert "sensevoice" in rocm.local_asr_engines
    assert cuda.sensevoice_status == "compatibility"
    assert cpu.sensevoice_status == "official"
    assert rocm.sensevoice_status == "experimental"
    assert cuda.sensevoice_model_ids == ("iic/SenseVoiceSmall",)


def test_nvidia_parakeet_uses_sherpa_only_in_cpu_profile():
    cuda = get_runtime_capabilities("cuda")
    cpu = get_runtime_capabilities("cpu")
    rocm = get_runtime_capabilities("rocm")

    assert "parakeet-ctc-ja" in cuda.local_asr_engines
    assert "parakeet-ctc-ja" in cpu.local_asr_engines
    assert "parakeet-ctc-ja" not in rocm.local_asr_engines
    assert cuda.parakeet_status == "experimental"
    assert cpu.parakeet_status == "official"
    assert rocm.parakeet_status == "disabled"
    assert cuda.parakeet_model_ids == (
        "nvidia/parakeet-tdt_ctc-0.6b-ja",
        "nvidia/parakeet-tdt_ctc-1.1b",
        "grider-transwithai/parakeet-ctc-1.1b-ja",
    )
    assert cpu.parakeet_model_ids == (
        "nvidia/parakeet-tdt-0.6b-v3",
        "nvidia/parakeet-tdt_ctc-0.6b-ja",
    )


def test_asr_model_capabilities_distinguish_fixed_and_multilingual_models():
    capabilities = {
        item["model_id"]: item for item in list_asr_model_capabilities()
    }

    assert capabilities["nvidia/parakeet-tdt_ctc-1.1b"]["language_mode"] == "fixed"
    assert capabilities["nvidia/parakeet-tdt_ctc-1.1b"]["supported_languages"] == ["en"]
    assert capabilities["nvidia/parakeet-tdt-0.6b-v3"]["language_mode"] == "multilingual"
    assert capabilities["nvidia/parakeet-tdt-0.6b-v3"]["default_language"] == "auto"
    assert len(capabilities["nvidia/parakeet-tdt-0.6b-v3"]["supported_languages"]) == 25
    assert capabilities["FunAudioLLM/Fun-ASR-Nano-2512"]["supported_languages"] == [
        "zh", "en", "ja"
    ]
    assert len(
        capabilities["FunAudioLLM/Fun-ASR-MLT-Nano-2512"]["supported_languages"]
    ) == 31


def test_model_language_is_coerced_by_backend():
    assert coerce_model_language("nvidia/parakeet-tdt_ctc-1.1b", "ja") == "en"
    assert coerce_model_language(
        "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame", "en"
    ) == "ja"
    assert coerce_model_language("FunAudioLLM/Fun-ASR-Nano-2512", "de") == "auto"
    assert coerce_model_language("FunAudioLLM/Fun-ASR-MLT-Nano-2512", "sv") == "sv"


def test_qwen3_anime_model_replaces_legacy_ja_model():
    cuda = get_runtime_capabilities("cuda")
    rocm = get_runtime_capabilities("rocm")

    expected_model = "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame"
    assert expected_model in cuda.qwen3_asr_model_ids
    assert expected_model in rocm.qwen3_asr_model_ids
    assert "neosophie/Qwen3-ASR-1.7B-JA" not in cuda.qwen3_asr_model_ids


def test_legacy_qwen3_ja_config_migrates_to_anime_model():
    config = _config_for("cuda")
    config["transcription"].update({
        "backend": "qwen3-asr",
        "use_sensevoice_asr": False,
        "use_qwen3_asr": True,
        "qwen3_asr_model": "neosophie/Qwen3-ASR-1.7B-JA",
    })

    args = _manager().to_main_args(config)

    assert args["model"] == "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame"


def test_sensevoice_config_maps_to_cli_args_for_cuda():
    args = _manager().to_main_args(_config_for("cuda"))

    assert args["model"] == "iic/SenseVoiceSmall"
    assert args["use_sensevoice_asr"] is True
    assert args["use_qwen3_asr"] is False
    assert args["sensevoice_model"] == "iic/SenseVoiceSmall"
    assert args["sensevoice_device"] == "auto"
    assert args["preload_asr_model"] is True
    assert args["keep_asr_loaded"] is True


def test_nvidia_parakeet_ja_config_maps_to_cli_args_for_cuda():
    config = _config_for("cuda")
    config["transcription"].update({
        "backend": "parakeet-ctc-ja",
        "use_sensevoice_asr": False,
        "use_nemo_asr": True,
        "nemo_asr_model": "nvidia/parakeet-tdt_ctc-0.6b-ja",
        "nemo_asr_dtype": "bfloat16",
        "language": "ja",
    })

    args = _manager().to_main_args(config)

    assert args["model"] == "nvidia/parakeet-tdt_ctc-0.6b-ja"
    assert args["use_nemo_asr"] is True
    assert args["use_qwen3_asr"] is False
    assert args["use_sensevoice_asr"] is False
    assert args["nemo_asr_model"] == "nvidia/parakeet-tdt_ctc-0.6b-ja"
    assert args["nemo_asr_device"] == "auto"
    assert args["nemo_asr_decoding"] == "tdt"
    assert args["language"] == "ja"
    assert args["nemo_asr_dtype"] == "bfloat16"
    assert args["preload_asr_model"] is True
    assert args["keep_asr_loaded"] is True


def test_nvidia_parakeet_en_model_forces_english_language():
    config = _config_for("cuda")
    config["transcription"].update({
        "backend": "parakeet-ctc-ja",
        "use_sensevoice_asr": False,
        "use_nemo_asr": True,
        "nemo_asr_model": "nvidia/parakeet-tdt_ctc-1.1b",
        "language": "ja",
    })

    args = _manager().to_main_args(config)

    assert args["model"] == "nvidia/parakeet-tdt_ctc-1.1b"
    assert args["language"] == "en"


def test_cpu_parakeet_coerces_legacy_model_to_sherpa_model():
    config = _config_for("cpu")
    config["transcription"].update({
        "backend": "parakeet-ctc-ja",
        "use_sensevoice_asr": False,
        "use_nemo_asr": True,
        "nemo_asr_model": "grider-transwithai/parakeet-ctc-1.1b-ja",
    })

    args = _manager().to_main_args(config)

    assert args["use_nemo_asr"] is True
    assert args["use_qwen3_asr"] is False
    assert args["model"] == "nvidia/parakeet-tdt-0.6b-v3"


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


def test_conflicting_asr_flags_are_normalized_to_one_backend():
    config = _config_for("cuda")
    config["transcription"].update({
        "backend": "qwen3-asr",
        "use_qwen3_asr": True,
        "use_sensevoice_asr": True,
        "use_nemo_asr": True,
        "qwen3_asr_model": "Qwen/Qwen3-ASR-1.7B",
        "nemo_asr_model": "grider-transwithai/parakeet-ctc-1.1b-ja",
    })

    args = _manager().to_main_args(config)

    enabled_flags = [
        args["use_openai_transcription_api"],
        args["use_qwen3_asr"],
        args["use_sensevoice_asr"],
        args["use_nemo_asr"],
    ]
    assert enabled_flags.count(True) == 1
    assert args["use_sensevoice_asr"] is True
    assert args["model"] == "iic/SenseVoiceSmall"


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


def test_live_audio_settings_map_to_runtime_args():
    config = _config_for("cuda")
    config["input"]["device_recording_interval"] = 0.1
    config["audio_slicing_vad"] = {
        "min_audio_length": 0.7,
        "target_audio_length": 3.0,
        "max_audio_length": 6.0,
        "continuous_no_speech_threshold": 0.5,
        "disable_dynamic_no_speech_threshold": True,
        "prefix_retention_length": 0.25,
        "vad_enabled": False,
        "vad_threshold": 0.35,
        "disable_dynamic_vad_threshold": True,
        "vad_every_n_frames": 3,
        "vad_backend": "silero",
        "firered_vad_model_path": "",
    }

    args = _manager().to_main_args(config)

    assert args["device_recording_interval"] == 0.1
    assert args["min_audio_length"] == 0.7
    assert args["target_audio_length"] == 3.0
    assert args["max_audio_length"] == 6.0
    assert args["continuous_no_speech_threshold"] == 0.5
    assert args["disable_dynamic_no_speech_threshold"] is True
    assert args["prefix_retention_length"] == 0.25
    assert args["disable_vad"] is True
    assert args["vad_threshold"] == 0.35
    assert args["disable_dynamic_vad_threshold"] is True
    assert args["vad_every_n_frames"] == 3
    assert args["vad_backend"] == "silero"


def test_translation_backend_selects_provider_without_api_key_heuristics():
    config = _config_for("cuda")
    config["general"] = {
        "openai_api_key": "openai-key",
        "google_api_key": "google-key",
    }
    config["translation"] = {
        "backend": "custom:local-hymt",
        "translation_prompt": "翻譯為繁體中文",
        "translation_model_family": "hy_mt2",
        "translation_output_format": "text",
        "translation_max_concurrency": 1,
        "translation_max_output_tokens": 128,
        "paired_subtitle_mode": True,
        "custom_models": [{
            "name": "local-hymt",
            "model_name": "localllm",
            "base_url": "http://127.0.0.1:8080",
            "api_key": "local",
        }],
    }

    args = _manager().to_main_args(config)

    assert args["translation_provider"] == "openai_compatible"
    assert args["translation_model_family"] == "hy_mt2"
    assert args["translation_output_format"] == "text"
    assert args["translation_max_concurrency"] == 1
    assert args["translation_max_output_tokens"] == 128
    assert args["disable_paired_subtitle_mode"] is False
    assert args["disable_asr_overlap_deduplication"] is False
    assert args["disable_subtitle_assembler"] is False
    assert args["subtitle_assembler_wait_ms"] == 400
    assert args["google_api_key"] == "google-key"


def test_fun_asr_nano_models_are_profile_aware():
    expected = (
        "FunAudioLLM/Fun-ASR-Nano-2512",
        "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
    )
    cuda = get_runtime_capabilities("cuda")
    cpu = get_runtime_capabilities("cpu")
    rocm = get_runtime_capabilities("rocm")

    assert cuda.fun_asr_model_ids == expected
    assert cpu.fun_asr_model_ids == ("FunAudioLLM/Fun-ASR-Nano-2512",)
    assert rocm.fun_asr_model_ids == expected
    assert cuda.fun_asr_status == "compatibility"
    assert cpu.fun_asr_status == "official"
    assert rocm.fun_asr_status == "experimental"
    assert all("fun-asr-nano" in profile.local_asr_engines for profile in (cuda, cpu, rocm))


def test_fun_asr_mlt_config_maps_to_main_args():
    config = _config_for("cuda")
    config["transcription"].update(
        {
            "backend": "fun-asr-nano",
            "model": "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
            "use_qwen3_asr": False,
            "use_sensevoice_asr": False,
            "use_fun_asr": True,
            "fun_asr_model": "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
        }
    )

    args = _manager().to_main_args(config)

    assert args["use_fun_asr"] is True
    assert args["use_qwen3_asr"] is False
    assert args["model"] == "FunAudioLLM/Fun-ASR-MLT-Nano-2512"
    assert args["fun_asr_model"] == "FunAudioLLM/Fun-ASR-MLT-Nano-2512"
    assert args["fun_asr_device"] == "auto"


def test_fun_asr_command_reprobes_stale_runtime_capabilities(monkeypatch):
    from backend.core import translator as translator_module
    from backend.core.translator import TranslationContext

    config = _config_for("cuda")
    config["transcription"].update(
        {
            "backend": "fun-asr-nano",
            "use_qwen3_asr": False,
            "use_sensevoice_asr": False,
            "use_fun_asr": True,
            "fun_asr_model": "FunAudioLLM/Fun-ASR-Nano-2512",
        }
    )
    args = _manager().to_main_args(config)
    probes = iter(
        (
            frozenset({"model", "language"}),
            frozenset({
                "model", "language", "use_fun_asr", "fun_asr_model", "fun_asr_device",
            }),
        )
    )

    monkeypatch.setattr(
        translator_module,
        "_get_supported_cli_args",
        type(
            "Probe",
            (),
            {
                "__call__": staticmethod(lambda *_: next(probes)),
                "cache_clear": staticmethod(lambda: None),
            },
        )(),
    )
    monkeypatch.setattr(
        translator_module,
        "_resolve_profile_python",
        lambda *_: "python",
    )

    command = TranslationContext(args, "fun-asr-test")._build_command()

    assert "--use_fun_asr" in command
    assert command[command.index("--fun_asr_model") + 1] == "FunAudioLLM/Fun-ASR-Nano-2512"
