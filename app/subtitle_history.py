"""Dependency-free helpers for native subtitle history and viewport selection."""

from __future__ import annotations

from typing import Any


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
