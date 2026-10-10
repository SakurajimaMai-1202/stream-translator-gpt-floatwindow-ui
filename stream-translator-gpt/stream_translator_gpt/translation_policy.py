from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TranslationCapabilities:
    model_family: str
    supports_system_prompt: bool
    supports_structured_output: bool
    preferred_output_format: str
    default_max_concurrency: int
    temperature: float
    top_p: float
    top_k: int | None = None
    repetition_penalty: float | None = None


@dataclass(frozen=True)
class TranslationRequest:
    segment_id: int
    source_text: str
    previous_original: str = ""
    previous_translation: str = ""
    glossary: dict[str, str] | None = None
    previous_sources: tuple[str, ...] = ()
    source_language: str = "auto"
    target_language: str = "Traditional Chinese"
    candidates: dict[str, str] | None = None
    preserve_elements: tuple[str, ...] = ()
    repair: bool = False
    session_id: int = 0


@dataclass(frozen=True)
class PreparedPrompt:
    system_instruction: str | None
    user_content: str
    output_format: str
    temperature: float
    top_p: float
    top_k: int | None
    repetition_penalty: float | None


@dataclass
class TranslationResult:
    segment_id: int
    translation: str = ""
    provider: str = ""
    model: str = ""
    queue_latency_ms: float | None = None
    generation_latency_ms: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    error: str | None = None
    validation_reasons: tuple[str, ...] = ()
    matched_terms: dict[str, str] | None = None
    retry_count: int = 0


_CAPABILITY_PRESETS = {
    "index_translate": TranslationCapabilities(
        model_family="index_translate", supports_system_prompt=False,
        supports_structured_output=False, preferred_output_format="text",
        default_max_concurrency=1, temperature=0.0, top_p=1.0,
    ),
    "hy_mt2": TranslationCapabilities(
        model_family="hy_mt2",
        supports_system_prompt=False,
        supports_structured_output=False,
        preferred_output_format="text",
        default_max_concurrency=1,
        temperature=0.7,
        top_p=0.6,
        top_k=20,
        repetition_penalty=1.05,
    ),
    "generic_chat": TranslationCapabilities(
        model_family="generic_chat",
        supports_system_prompt=True,
        supports_structured_output=False,
        preferred_output_format="text",
        default_max_concurrency=1,
        temperature=0.0,
        top_p=0.9,
    ),
    "structured_api": TranslationCapabilities(
        model_family="structured_api",
        supports_system_prompt=True,
        supports_structured_output=True,
        preferred_output_format="json",
        default_max_concurrency=2,
        temperature=0.0,
        top_p=0.9,
    ),
}


def resolve_model_family(requested: str | None, model: str, provider: str) -> str:
    normalized = str(requested or "auto").strip().lower().replace("-", "_")
    aliases = {
        "hymt2": "hy_mt2",
        "hy_mt": "hy_mt2",
        "generic": "generic_chat",
        "chat": "generic_chat",
        "structured": "structured_api",
        "index": "index_translate",
        "indextranslate": "index_translate",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in _CAPABILITY_PRESETS:
        return normalized

    model_lower = str(model or "").lower()
    if re.search(r"index[-_ ]?translate(?:[-_/ .]|$)", model_lower):
        return "index_translate"
    if "hy-mt2" in model_lower or "hymt2" in model_lower:
        return "hy_mt2"
    if provider in {"openai", "gemini"}:
        return "structured_api"
    return "generic_chat"


def get_capabilities(model_family: str) -> TranslationCapabilities:
    return _CAPABILITY_PRESETS.get(model_family, _CAPABILITY_PRESETS["generic_chat"])


def resolve_output_format(requested: str | None, capabilities: TranslationCapabilities) -> str:
    normalized = str(requested or "auto").strip().lower()
    if normalized == "json" and capabilities.supports_structured_output:
        return "json"
    if normalized == "text":
        return "text"
    return capabilities.preferred_output_format


def _matching_glossary(source_text: str, glossary: dict[str, str], limit: int = 20) -> dict[str, str]:
    source_lower = source_text.lower()
    matches = (
        (source, target)
        for source, target in glossary.items()
        if str(source).lower() in source_lower
    )
    return dict(sorted(matches, key=lambda item: len(str(item[0])), reverse=True)[:limit])


class TranslationPromptStrategy:
    def __init__(self, prompt: str, capabilities: TranslationCapabilities, output_format: str):
        self.prompt = str(prompt or "").strip()
        self.capabilities = capabilities
        self.output_format = output_format

    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
        glossary = _matching_glossary(request.source_text, request.glossary or {})
        glossary_line = ""
        if glossary:
            pairs = ", ".join(f"{source}→{target}" for source, target in glossary.items())
            glossary_line = f"Glossary: {pairs}\n"
        context = ""
        if request.previous_original:
            context = (
                "Previous subtitle for context only. Do not repeat it:\n"
                f"{request.previous_original}\n\n"
            )
        user_content = f"{glossary_line}{context}{self.prompt}:\n{request.source_text}".strip()
        system_instruction = (
            "You are a professional translator. Translate accurately and concisely. "
            "Output only the translation without explanations or Markdown."
        )
        if self.output_format == "json":
            system_instruction += ' Return JSON with exactly one key named "translation".'
        return PreparedPrompt(
            system_instruction=system_instruction,
            user_content=user_content,
            output_format=self.output_format,
            temperature=self.capabilities.temperature,
            top_p=self.capabilities.top_p,
            top_k=self.capabilities.top_k,
            repetition_penalty=self.capabilities.repetition_penalty,
        )


class HyMT2PromptStrategy(TranslationPromptStrategy):
    optimizer_settings = None

    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
        if self.optimizer_settings is not None:
            from .hy_mt2_optimizer import build_prompt
            prompt = build_prompt(request.source_text, self.prompt,
                                  request.glossary or {}, request.previous_sources,
                                  self.optimizer_settings)
            additions = []
            if request.preserve_elements:
                additions.append("〖必須原樣保留，數量及順序不變〗\n" + "、".join(request.preserve_elements))
            if request.candidates and not request.repair:
                candidates = _matching_glossary(request.source_text, request.candidates,
                                               self.optimizer_settings.max_terms)
                if candidates:
                    additions.append("〖不確定辨識候選，僅供消歧，不得強制改寫〗\n" + str(candidates))
            if additions:
                prompt = "\n\n".join(additions + [prompt])
            return PreparedPrompt(
                system_instruction=None,
                user_content=prompt,
                output_format="text",
                temperature=self.capabilities.temperature,
                top_p=self.capabilities.top_p,
                top_k=self.capabilities.top_k,
                repetition_penalty=self.capabilities.repetition_penalty,
            )
        blocks = []
        glossary = _matching_glossary(request.source_text, request.glossary or {})
        if glossary:
            terms = "\n".join(f"{source} 翻译成 {target}" for source, target in glossary.items())
            blocks.append(f"参考下面的翻译：\n{terms}")
        if request.previous_original:
            blocks.append(
                "〖背景信息，仅供理解，不要翻译或重复〗\n"
                f"{request.previous_original}"
            )
        blocks.append(f"{self.prompt}：\n{request.source_text}")
        return PreparedPrompt(
            system_instruction=None,
            user_content="\n\n".join(blocks),
            output_format="text",
            temperature=self.capabilities.temperature,
            top_p=self.capabilities.top_p,
            top_k=self.capabilities.top_k,
            repetition_penalty=self.capabilities.repetition_penalty,
        )


class IndexTranslatePromptStrategy(TranslationPromptStrategy):
    """instTrans single-user format; constraints do not imply JSON decoding."""
    optimizer_settings = None

    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
        settings = self.optimizer_settings
        target = request.target_language or "Traditional Chinese"
        if target.lower().replace("_", "-") in {"traditional chinese", "zh-tw", "zh-hant"}:
            target = "繁體中文（台灣用語）"
        constraints = []
        background = ""
        if settings is not None:
            if not request.repair:
                if re.search(r"[\u3040-\u30ff]", request.source_text):
                    constraints.append("【注意】 普通日语词语、助词及语气词都要翻成目标语言，不要留下日文；只按指定术语表或保留要求保留原文专名。")
            terms = _matching_glossary(request.source_text, request.glossary or {}, settings.max_terms)
            if terms:
                constraints.append("【硬性要求】 专名/术语对照: " + "、".join(f"{s}→{t}" for s, t in terms.items()))
            for element in request.preserve_elements:
                if element and element in request.source_text:
                    constraints.append(f"【硬性要求】 原样保留 {element} 的数量及出现顺序。")
            if not request.repair:
                if settings.style and settings.style_text.strip():
                    constraints.append("【注意】 " + settings.style_text.strip()[:500])
                if settings.preferences.strip():
                    constraints.append("【注意】 " + settings.preferences.strip()[:500])
                candidates = _matching_glossary(request.source_text, request.candidates or {}, settings.max_terms)
                if candidates:
                    constraints.append("【注意】 以下是不确定的辨识候选，仅供消歧，不得强制改写原文：" + str(candidates))
                remaining = settings.max_context_chars
                context = []
                for source in reversed(request.previous_sources[-settings.context_window:] if settings.context_window else ()):
                    if source.strip() and len(source) <= remaining:
                        context.insert(0, source)
                        remaining -= len(source)
                if context:
                    background = ("【背景参考】\n以下是之前的原文，仅用于理解。不要翻译、复述或输出本区块。\n"
                                  + "\n".join(context) + "\n【背景参考结束】\n\n")
                    constraints.append("【注意】 只翻译【源文】到【源文结束】之间的本次原文，包括语气词；即使句子尚未说完，也翻译现有内容，不要等待后文或输出空白。")
        if constraints:
            content = (f"请将以下文本翻译成{target}，并且严格遵循所有约束要求。\n\n【源文】\n"
                       + request.source_text.strip() + "\n【源文结束】\n\n【约束要求】\n"
                       + "\n".join(f"{i}. {value}" for i, value in enumerate(constraints, 1))
                       + "\n\n只输出译文，不要有任何额外说明。")
        else:
            content = f"请将以下文本翻译为{target}，直接输出翻译结果，不要进行任何解释。\n\n{request.source_text.strip()}"
        if background:
            content = background + content
        return PreparedPrompt(None, content, "text", 0.0, 1.0, None, None)


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str = "error"


def validate_translation(request: TranslationRequest, translation: str,
                         history: tuple[tuple[str, str], ...] = ()) -> tuple[ValidationIssue, ...]:
    from .hy_mt2_output_validation import repeats_previous_translation
    issues = []
    if not str(translation or "").strip():
        return (ValidationIssue("empty_output"),)
    target_language = str(request.target_language or "").strip().lower().replace("_", "-")
    if target_language in {"traditional chinese", "simplified chinese", "chinese", "zh", "zh-tw", "zh-hant", "zh-cn", "zh-hans", "繁體中文", "繁体中文", "简体中文"}:
        # Only reject exact Japanese copies. Names and explicitly preserved spans
        # can legitimately retain kana; Chinese-only phrases can match the source.
        source = request.source_text.strip()
        remainder = source
        for element in request.preserve_elements:
            if element:
                remainder = remainder.replace(element, "")
        for term, fixed in (request.glossary or {}).items():
            if term == fixed and term:
                remainder = remainder.replace(term, "")
        if translation.strip() == source and re.search(r"[\u3041-\u3096]", remainder):
            issues.append(ValidationIssue("untranslated_source"))
        output_remainder = translation
        for element in request.preserve_elements:
            if element:
                output_remainder = output_remainder.replace(element, "")
        for fixed in (request.glossary or {}).values():
            if fixed:
                output_remainder = output_remainder.replace(fixed, "")
        kana_count = len(re.findall(r"[\u3041-\u3096]", output_remainder))
        if kana_count >= 3 and kana_count / max(1, len(output_remainder.strip())) >= 0.25:
            issues.append(ValidationIssue("target_language_mismatch"))
        # Sparse common words can hide inside an otherwise Chinese sentence.
        # Compare whole kana runs so a name containing a substring is exempt.
        common_words = {'まさか', 'もしかして', 'けれども', 'だから', 'でも',
                        'なんか', 'です', 'でした', 'ですね', 'ですよ', 'でしょう',
                        'ごめん', 'ありがとう', 'たぶん', 'もちろん', 'まあ'}
        if (common_words.intersection(re.findall(r"[\u3041-\u3096]+", output_remainder))
                and not any(issue.code == 'target_language_mismatch' for issue in issues)):
            issues.append(ValidationIssue('target_language_mismatch'))
        # Catch newly generated broken romanizations such as Moemoebaウ without
        # banning katakana names or names explicitly preserved by the glossary.
        hybrids = re.findall(r'(?<![A-Za-z])[A-Za-z]{4,}[\u30a1-\u30fa]{1,2}(?![\u30a1-\u30fa])', output_remainder)
        if any(token not in request.source_text for token in hybrids):
            if not any(issue.code == 'target_language_mismatch' for issue in issues):
                issues.append(ValidationIssue('target_language_mismatch'))
    if '\n' in translation and '\n' not in request.source_text:
        if request.previous_sources and len([line for line in translation.splitlines() if line.strip()]) > 1:
            # A single live segment has no requested line layout. Multiple lines
            # in a contextual reply can be a translation of the background.
            issues.append(ValidationIssue('unexpected_multiline_output'))
        from .hy_mt2_output_validation import _comparable
        lines = [_comparable(line) for line in translation.splitlines()]
        for previous_source, previous_output in history[-3:]:
            old = _comparable(previous_output)
            if len(old) >= 4 and old in lines and _comparable(previous_source) != _comparable(request.source_text):
                if not any(issue.code == 'context_echo_rejected' for issue in issues):
                    issues.append(ValidationIssue('context_echo_rejected'))
                break
    if any(marker in translation and marker not in request.source_text
           for marker in ("【源文】", "【约束要求】", "【硬性要求】", "〖背景資訊", "<think>")):
        issues.append(ValidationIssue("prompt_leakage"))
    if repeats_previous_translation(request.source_text, translation, history):
        issues.append(ValidationIssue("context_echo_rejected"))
    if any(target not in translation for target in _matching_glossary(request.source_text, request.glossary or {}, len(request.glossary or {})).values() if target):
        issues.append(ValidationIssue("fixed_term_missing"))
    elements = [element for element in request.preserve_elements if element and element in request.source_text]
    if any(translation.count(e) != request.source_text.count(e) for e in elements):
        issues.append(ValidationIssue("preserve_element_changed"))
    elif elements:
        pattern = "|".join(re.escape(e) for e in sorted(set(elements), key=len, reverse=True))
        if re.findall(pattern, translation) != re.findall(pattern, request.source_text):
            issues.append(ValidationIssue("preserve_element_order"))
    return tuple(issues)


def create_prompt_strategy(
    model_family: str,
    prompt: str,
    output_format: str,
) -> TranslationPromptStrategy:
    capabilities = get_capabilities(model_family)
    if model_family == "hy_mt2":
        return HyMT2PromptStrategy(prompt, capabilities, "text")
    if model_family == "index_translate":
        return IndexTranslatePromptStrategy(prompt, capabilities, "text")
    return TranslationPromptStrategy(prompt, capabilities, output_format)


def parse_translation_output(completion: Any, output_format: str) -> str:
    text = str(completion or "").strip()
    if text.startswith("```") and text.endswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    if output_format != "json":
        return text

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return text
    try:
        payload = json.loads(match.group(0))
    except (json.JSONDecodeError, TypeError):
        return text
    translation = payload.get("translation")
    return str(translation).strip() if translation else text
