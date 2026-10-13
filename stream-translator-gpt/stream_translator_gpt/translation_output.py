from .qwen3_asr_postprocess import (
    is_traditional_chinese_target,
    normalize_chinese_script,
    strip_unknown_token,
)


class TranslationOutputConversionError(RuntimeError):
    code = "translation_script_conversion_failed"


def normalize_translation_output(text: str, target_language: str | None, converter=None) -> str:
    """Normalize model output to the target script; converter defaults to normalize_chinese_script."""
    convert = converter or normalize_chinese_script
    text = strip_unknown_token(text)
    language = str(target_language or "").strip().lower().replace("_", "-")
    if is_traditional_chinese_target(language):
        try:
            return convert(text, "zh-tw")
        except Exception as exc:
            if "opencc" in str(exc).lower() and any(
                    word in str(exc).lower() for word in ("requires", "no module", "unavailable")):
                raise TranslationOutputConversionError(
                    "OpenCC unavailable: Traditional Chinese translation requires OpenCC (opencc-python-reimplemented); "
                    "the translation runtime is missing this dependency."
                ) from exc
            raise TranslationOutputConversionError("Traditional Chinese translation script conversion failed.") from exc
    return text
