import re

from .qwen3_asr_postprocess import (
    is_traditional_chinese_target,
    normalize_chinese_script,
    strip_unknown_token,
)


# Only Latin and katakana names are safe to convert before kana validation.
_NAME_HONORIFIC = re.compile(r"(?<=[A-Za-z0-9\u30a1-\u30fa\u30fc])(さん|ちゃん|くん)(?=[^\u3041-\u3096]|$|[\u306f\u304c\u306e\u306b\u3092\u3082\u3068\u3067\u3078\u3084\u304b\u306d\u3088](?![\u3041-\u3096]))")
_HONORIFIC_ZH = {"さん": "桑", "ちゃん": "醬", "くん": "君"}


def localize_name_honorifics(text: str) -> str:
    return _NAME_HONORIFIC.sub(lambda match: _HONORIFIC_ZH[match.group(1)], text)


class TranslationOutputConversionError(RuntimeError):
    code = "translation_script_conversion_failed"


def normalize_translation_output(text: str, target_language: str | None, converter=None) -> str:
    """Normalize model output to the target script; converter defaults to normalize_chinese_script."""
    convert = converter or normalize_chinese_script
    text = strip_unknown_token(text)
    language = str(target_language or "").strip().lower().replace("_", "-")
    if "chinese" in language or language.startswith("zh") or "中文" in language:
        text = localize_name_honorifics(text)
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
