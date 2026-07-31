from stream_translator_gpt.asr_preload import build_asr_config


def test_build_asr_config_selects_fun_asr_backend():
    config = build_asr_config(
        {
            "use_fun_asr": True,
            "fun_asr_model": "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
            "fun_asr_device": "auto",
            "language": "vi",
        }
    )

    assert config.backend == "fun_asr"
    assert config.fun_asr_model == "FunAudioLLM/Fun-ASR-MLT-Nano-2512"
    assert config.fun_asr_device == "auto"
    assert config.language == "vi"
