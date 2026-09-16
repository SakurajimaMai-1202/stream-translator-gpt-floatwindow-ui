"""Dependency-free helpers for native subtitle history and viewport selection."""

from __future__ import annotations

import re
from typing import Any


TIMESTAMP_DRIFT_TOLERANCE_MS = 50
_TIMESTAMP_RANGE_RE = re.compile(
    r"(?P<start>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})\s*(?:-->|->|→)\s*"
    r"(?P<end>\d{1,2}:\d{2}:\d{2}[,.]\d{1,3})"
)


def _clock_to_ms(value: str) -> int | None:
    match = re.fullmatch(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})", value.strip())
    if not match:
        return None
    hours, minutes, seconds, milliseconds = match.groups()
    milliseconds = milliseconds.ljust(3, "0")
    return (((int(hours) * 60 + int(minutes)) * 60) + int(seconds)) * 1000 + int(milliseconds)


def _timestamp_range_ms(data: dict[str, Any]) -> tuple[int, int] | None:
    timestamp = data.get("backend_timestamp") or data.get("timestamp")
    if timestamp is None:
        return None
    match = _TIMESTAMP_RANGE_RE.search(str(timestamp))
    if not match:
        return None
    start = _clock_to_ms(match.group("start"))
    end = _clock_to_ms(match.group("end"))
    if start is None or end is None:
        return None
    return start, end


def subtitle_identity(data: dict[str, Any]) -> tuple[str, str] | None:
    """Return the stable identity shared by partial and translated updates."""
    segment_id = data.get("segment_id")
    if segment_id is not None and segment_id != "":
        return ("segment", str(segment_id))

    timestamp = data.get("backend_timestamp") or data.get("timestamp")
    if timestamp is not None and timestamp != "":
        return ("timestamp", str(timestamp))

    item_id = data.get("id")
    if item_id is not None and item_id != "":
        return ("id", str(item_id))
    return None


def find_subtitle_index(lines: list[dict[str, Any]], incoming: dict[str, Any]) -> int:
    """Match an update even when it transitions from timestamp-only to segment ID."""
    segment_id = incoming.get("segment_id")
    if segment_id is not None and segment_id != "":
        segment_value = str(segment_id)
        for index, line in enumerate(lines):
            existing = line.get("segment_id")
            if existing is not None and existing != "" and str(existing) == segment_value:
                return index

    timestamp = incoming.get("backend_timestamp") or incoming.get("timestamp")
    if timestamp is not None and timestamp != "":
        timestamp_value = str(timestamp)
        for index, line in enumerate(lines):
            existing = line.get("backend_timestamp") or line.get("timestamp")
            if existing is not None and existing != "" and str(existing) == timestamp_value:
                return index

        # ASR emits a timestamp-only event first, then a translated event with
        # segment_id. Container rounding can shift one boundary by 1 ms. Treat
        # it as the same row only when the text and both time boundaries agree
        # within a small tolerance.
        incoming_range = _timestamp_range_ms(incoming)
        incoming_original = str(incoming.get("original") or "").strip()
        if incoming_range is not None and incoming_original:
            for index in range(len(lines) - 1, -1, -1):
                line = lines[index]
                if str(line.get("original") or "").strip() != incoming_original:
                    continue
                existing_range = _timestamp_range_ms(line)
                if existing_range is None:
                    continue
                if (
                    abs(existing_range[0] - incoming_range[0]) <= TIMESTAMP_DRIFT_TOLERANCE_MS
                    and abs(existing_range[1] - incoming_range[1]) <= TIMESTAMP_DRIFT_TOLERANCE_MS
                ):
                    return index

    item_id = incoming.get("id")
    if item_id is not None and item_id != "":
        item_value = str(item_id)
        for index, line in enumerate(lines):
            existing = line.get("id")
            if existing is not None and existing != "" and str(existing) == item_value:
                return index
    return -1


def entries_fitting_height(entries: list[dict[str, Any]], available_height: int) -> list[dict[str, Any]]:
    """Keep the newest entries that fit, while always returning at least one."""
    if not entries:
        return []

    selected: list[dict[str, Any]] = []
    used = 0
    for entry in reversed(entries):
        height = max(0, int(entry.get("height", 0)))
        if selected and used + height > available_height:
            break
        selected.append(entry)
        used += height
        if used >= available_height:
            break
    selected.reverse()
    return selected
