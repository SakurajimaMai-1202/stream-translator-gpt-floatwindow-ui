"""Bounded, opt-in prompt construction for live HY-MT2 subtitles."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OptimizerSettings:
    context_window: int = 3
    max_context_chars: int = 1000
    max_terms: int = 10
    style: bool = True
    style_text: str = ""
    preferences: str = ""


def build_prompt(source: str, prompt: str, glossary: dict[str, str],
                 previous_sources: tuple[str, ...], settings: OptimizerSettings) -> str:
    blocks = []
    if settings.style and settings.style_text.strip():
        blocks.append("〖翻譯要求〗\n" + settings.style_text.strip()[:500])
    if settings.preferences.strip():
        blocks.append("〖個人翻譯偏好〗\n" + settings.preferences.strip()[:500])
    source_lower = source.lower()
    matches = [(key, value) for key, value in glossary.items()
               if key and key.lower() in source_lower and value]
    matches.sort(key=lambda pair: (-len(pair[0]), pair[0]))
    if matches:
        terms = "\n".join(f"{key} 翻譯成 {value}"
                          for key, value in matches[:max(0, settings.max_terms)])
        if terms:
            blocks.append(f"〖術語〗\n{terms}")
    context = list(previous_sources[-max(0, settings.context_window):]) if settings.context_window else []
    if context:
        # Keep the newest complete utterances within the character budget.
        selected = []
        remaining = max(0, settings.max_context_chars)
        for line in reversed(context):
            line = line.strip()
            if line and len(line) <= remaining:
                selected.append(line)
                remaining -= len(line)
        if selected:
            blocks.append("〖背景資訊，僅供理解，不要翻譯或重複〗\n" + "\n".join(reversed(selected)))
    blocks.append(f"{prompt}：\n{source}")
    return "\n\n".join(blocks)
