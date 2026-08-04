from __future__ import annotations

from typing import Any, Literal


LanguageMode = Literal["fixed", "limited", "multilingual"]

QWEN3_LANGUAGES = (
    "zh", "en", "yue", "ar", "de", "fr", "es", "pt", "id", "it",
    "ko", "ru", "th", "vi", "ja", "tr", "hi", "ms", "nl", "sv",
    "da", "fi", "pl", "cs", "fil", "fa", "el", "ro", "hu", "mk",
)

FUN_ASR_MLT_LANGUAGES = (
    "zh", "en", "yue", "ja", "ko", "vi", "id", "th", "ms", "fil",
    "ar", "hi", "bg", "hr", "cs", "da", "nl", "et", "fi", "el",
    "hu", "ga", "lv", "lt", "mt", "pl", "pt", "ro", "sk", "sl", "sv",
)

SUPPORTED_UI_LANGUAGES = tuple(dict.fromkeys((*QWEN3_LANGUAGES, *FUN_ASR_MLT_LANGUAGES)))

WHISPER_MODEL_IDS = (
    "tiny", "base", "small", "medium", "large-v2", "large-v3", "large-v3-turbo",
)


def _entry(
    model_id: str,
    engine: str,
    language_mode: LanguageMode,
    supported_languages: tuple[str, ...],
    *,
    default_language: str = "auto",
    note: str = "",
) -> dict[str, Any]:
    return {
        "model_id": model_id,
        "engine": engine,
        "language_mode": language_mode,
        "supported_languages": list(supported_languages),
        "default_language": default_language,
        "note": note,
    }


ASR_MODEL_CAPABILITIES: dict[str, dict[str, Any]] = {
    **{
        model_id: _entry(
            model_id,
            "faster-whisper",
            "multilingual",
            SUPPORTED_UI_LANGUAGES,
            note="Multilingual Whisper model; auto language detection is available.",
        )
        for model_id in WHISPER_MODEL_IDS
    },
    "Qwen/Qwen3-ASR-0.6B": _entry(
        "Qwen/Qwen3-ASR-0.6B", "qwen3-asr", "multilingual", QWEN3_LANGUAGES
    ),
    "Qwen/Qwen3-ASR-1.7B": _entry(
        "Qwen/Qwen3-ASR-1.7B", "qwen3-asr", "multilingual", QWEN3_LANGUAGES
    ),
    "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame": _entry(
        "jaykwok/Qwen3-ASR-1.7B-JA-Anime-Galgame",
        "qwen3-asr",
        "fixed",
        ("ja",),
        default_language="ja",
        note="Japanese anime and galgame speech specialist.",
    ),
    "iic/SenseVoiceSmall": _entry(
        "iic/SenseVoiceSmall",
        "sensevoice",
        "limited",
        ("zh", "yue", "en", "ja", "ko"),
    ),
    "FunAudioLLM/Fun-ASR-Nano-2512": _entry(
        "FunAudioLLM/Fun-ASR-Nano-2512",
        "fun-asr-nano",
        "limited",
        ("zh", "en", "ja"),
        note="Standard Nano checkpoint: Chinese, English, and Japanese.",
    ),
    "FunAudioLLM/Fun-ASR-MLT-Nano-2512": _entry(
        "FunAudioLLM/Fun-ASR-MLT-Nano-2512",
        "fun-asr-nano",
        "multilingual",
        FUN_ASR_MLT_LANGUAGES,
        note="MLT checkpoint: 31 languages.",
    ),
    "nvidia/parakeet-tdt_ctc-0.6b-ja": _entry(
        "nvidia/parakeet-tdt_ctc-0.6b-ja",
        "parakeet-ctc-ja",
        "fixed",
        ("ja",),
        default_language="ja",
    ),
    "nvidia/parakeet-tdt-0.6b-v3": _entry(
        "nvidia/parakeet-tdt-0.6b-v3",
        "parakeet-ctc-ja",
        "fixed",
        ("en",),
        default_language="en",
        note="English Parakeet TDT model; CPU packages use sherpa-onnx INT8.",
    ),
    "nvidia/parakeet-tdt_ctc-1.1b": _entry(
        "nvidia/parakeet-tdt_ctc-1.1b",
        "parakeet-ctc-ja",
        "fixed",
        ("en",),
        default_language="en",
    ),
    "grider-transwithai/parakeet-ctc-1.1b-ja": _entry(
        "grider-transwithai/parakeet-ctc-1.1b-ja",
        "parakeet-ctc-ja",
        "fixed",
        ("ja",),
        default_language="ja",
    ),
}


def list_asr_model_capabilities() -> list[dict[str, Any]]:
    return [dict(entry) for entry in ASR_MODEL_CAPABILITIES.values()]


def normalize_language_code(language: str | None) -> str:
    normalized = str(language or "auto").strip().lower()
    aliases = {
        "": "auto",
        "zh-tw": "zh",
        "zh-hant": "zh",
        "zh-cn": "zh",
        "zh-hans": "zh",
        "chinese": "zh",
        "english": "en",
        "japanese": "ja",
        "korean": "ko",
        "cantonese": "yue",
        "tl": "fil",
    }
    return aliases.get(normalized, normalized)


def coerce_model_language(model_id: str, requested_language: str | None) -> str:
    capability = ASR_MODEL_CAPABILITIES.get(model_id)
    requested = normalize_language_code(requested_language)
    if not capability:
        return requested
    if capability["language_mode"] == "fixed":
        return str(capability["default_language"])
    supported = capability["supported_languages"]
    if requested == "auto" or requested in supported:
        return requested
    return str(capability["default_language"])
