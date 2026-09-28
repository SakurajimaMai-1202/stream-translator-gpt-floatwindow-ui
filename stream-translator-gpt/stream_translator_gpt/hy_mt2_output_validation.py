"""Conservative check for a HY-MT2 response that repeats prior subtitles."""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher


def _comparable(text: str) -> str:
    return "".join(char.casefold() for char in str(text or "")
                   if unicodedata.category(char)[0] not in {"P", "Z"})


def repeats_previous_translation(source: str, translation: str,
                                 history: tuple[tuple[str, str], ...]) -> bool:
    """Reject only a substantial near-copy of an unrelated previous output."""
    current_source = _comparable(source)
    if not current_source or not translation:
        return False
    output_lines = [_comparable(line) for line in translation.splitlines()]
    for previous_source, previous_translation in history[-3:]:
        old_source = _comparable(previous_source)
        old_output = _comparable(previous_translation)
        if len(old_output) < 12 or not old_source:
            continue
        # Repeated speech can legitimately have a repeated translation.
        if SequenceMatcher(None, current_source, old_source).ratio() >= 0.7:
            continue
        for line in output_lines:
            if (len(line) >= 12
                    and 0.65 <= len(line) / len(old_output) <= 1.35
                    and SequenceMatcher(None, line, old_output).ratio() >= 0.82):
                return True
    return False
