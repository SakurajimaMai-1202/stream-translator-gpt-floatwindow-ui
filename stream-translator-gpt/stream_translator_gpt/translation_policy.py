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


_CAPABILITY_PRESETS = {
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
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in _CAPABILITY_PRESETS:
        return normalized

    model_lower = str(model or "").lower()
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
    def prepare(self, request: TranslationRequest) -> PreparedPrompt:
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


def create_prompt_strategy(
    model_family: str,
    prompt: str,
    output_format: str,
) -> TranslationPromptStrategy:
    capabilities = get_capabilities(model_family)
    if model_family == "hy_mt2":
        return HyMT2PromptStrategy(prompt, capabilities, "text")
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
