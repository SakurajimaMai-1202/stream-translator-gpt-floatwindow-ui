from backend.core.config_manager import normalize_transcription_engine_flags


def test_explicit_engine_clears_stale_legacy_flags():
    transcription = {
        "backend": "sensevoice",
        "use_faster_whisper": True,
        "use_simul_streaming": True,
        "use_openai_transcription_api": True,
        "use_qwen3_asr": True,
        "use_sensevoice_asr": False,
        "use_fun_asr": True,
        "use_nemo_asr": True,
    }

    normalize_transcription_engine_flags(transcription)

    assert transcription["use_sensevoice_asr"] is True
    assert transcription["use_faster_whisper"] is False
    assert transcription["use_simul_streaming"] is False
    assert transcription["use_openai_transcription_api"] is False
    assert transcription["use_qwen3_asr"] is False
    assert transcription["use_fun_asr"] is False
    assert transcription["use_nemo_asr"] is False
