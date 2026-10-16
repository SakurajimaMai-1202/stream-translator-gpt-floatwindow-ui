import re

from .qwen3_asr_postprocess import (
    is_traditional_chinese_target,
    normalize_chinese_script,
    strip_unknown_token,
)


# A model often keeps the honorific after a name it romanized or left in
# katakana ("Shinoさん"). Only convert it after a non-hiragana character, so
# hiragana words such as みなさん or おじさん are left for the kana check.
_NAME_HONORIFIC = re.compile(r"(?<=[A-Za-z0-9\u30a1-\u30fa\u30fc\u4e00-\u9fff])(さん|ちゃん|くん)(?![\u3041-\u3096])")
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
