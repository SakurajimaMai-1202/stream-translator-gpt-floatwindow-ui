"""Normalize Qwen3-ASR protocol output and Chinese character variants."""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Any


_ASR_TEXT_MARKER = re.compile(r"<asr_text>", re.IGNORECASE)
_TRAILING_ASR_TEXT_MARKER = re.compile(r"</asr_text>\s*$", re.IGNORECASE)
_LEADING_LANGUAGE_MARKER = re.compile(
    r"^\s*language\s+[A-Za-z][A-Za-z _-]*?(?:\s*[:：]\s*|\s*\r?\n+)",
    re.IGNORECASE,
)
_SPECIAL_TOKEN = re.compile(r"<\|[^>]+\|>")

_TRADITIONAL_CHINESE = {
    "zh-tw", "zh-hant", "traditional chinese", "繁體中文", "繁体中文",
}
_SIMPLIFIED_CHINESE = {
    "zh-cn", "zh-hans", "simplified chinese", "簡體中文", "简体中文",
}


@lru_cache(maxsize=2)
def _opencc(config: str) -> Any:
    try:
        from opencc import OpenCC
    except ImportError as exc:
        raise RuntimeError(
            "Traditional/Simplified Chinese Qwen3-ASR output requires OpenCC. "
            "Install opencc-python-reimplemented."
        ) from exc
    return OpenCC(config)


def strip_qwen3_asr_markers(text: object) -> str:
    """Remove Qwen control markers without changing the recognized language."""
    normalized = str(text or "").strip()
    marker = _ASR_TEXT_MARKER.search(normalized)
    if marker:
        normalized = normalized[marker.end():]
    else:
        normalized = _LEADING_LANGUAGE_MARKER.sub("", normalized, count=1)
    normalized = _SPECIAL_TOKEN.sub("", normalized)
    normalized = _TRAILING_ASR_TEXT_MARKER.sub("", normalized).strip()
    return normalized


def normalize_chinese_script(text: object, output_language: str | None) -> str:
    """Deterministically enforce the Chinese script selected for ASR output."""
    normalized = str(text or "").strip()

    language = str(output_language or "").strip().lower().replace("_", "-")
    if language in _TRADITIONAL_CHINESE:
        return _opencc("s2twp").convert(normalized)
    if language in _SIMPLIFIED_CHINESE:
        return _opencc("t2s").convert(normalized)
    return normalized


def normalize_qwen3_asr_text(text: object, output_language: str | None) -> str:
    """Backward-compatible combined Qwen cleanup and script normalization."""
    return normalize_chinese_script(strip_qwen3_asr_markers(text), output_language)
