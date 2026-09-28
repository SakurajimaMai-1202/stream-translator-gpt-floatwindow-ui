"""Load user maintained HY-MT2 terminology files without provider coupling."""

from __future__ import annotations

import json
from pathlib import Path


def load_glossary_folder(folder: str | None) -> dict[str, str]:
    if not folder:
        return {}
    directory = Path(folder)
    if not directory.is_dir():
        raise ValueError(f"HY-MT2 glossary folder does not exist: {directory}")
    glossary: dict[str, str] = {}
    for path in sorted(directory.glob("*.json")):
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Invalid HY-MT2 glossary file {path}: {exc}") from exc
        if not isinstance(entries, dict):
            raise ValueError(f"HY-MT2 glossary file must contain an object: {path}")
        for source, record in entries.items():
            if isinstance(record, str):
                target, aliases = record, []
            elif isinstance(record, dict):
                target, aliases = record.get("target"), record.get("aliases", [])
            else:
                continue
            if not isinstance(source, str) or not isinstance(target, str) or not source or not target:
                continue
            glossary.setdefault(source, target)
            if isinstance(aliases, list):
                for alias in aliases:
                    if isinstance(alias, str) and alias.strip():
                        glossary.setdefault(alias.strip(), target)
    return glossary
