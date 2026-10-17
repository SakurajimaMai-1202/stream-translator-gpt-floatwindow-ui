"""Admin terminology learning and optional reading add-on routes."""
import asyncio
import json
import math
import os
import re
import unicodedata
from datetime import datetime, timezone
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from backend.core.logging_setup import resolve_log_dir
from backend.core.reading_addon_installer import reading_addon_installer, is_installed

router = APIRouter(prefix="/terminology", tags=["terminology"])


def _read_config():
    from backend.api.config import _read_config as read_config
    return read_config()


def suggestions_path():
    configured = os.environ.get("STREAM_TRANSLATOR_ASR_CORRECTION_LOG_DIR", "").strip()
    return (Path(configured).expanduser() if configured else resolve_log_dir()) / "asr_correction_suggestions.json"


def _normalize(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    value = "".join(chr(ord(c) - 0x60) if "\u30a1" <= c <= "\u30f6" else c for c in value)
    return re.sub(r"\s+", "", value).casefold()


def _list(value):
    return value if isinstance(value, list) else []


def read_suggestions():
    from backend.core.hy_mt2_glossary_presets import PRESET_ASR_VARIANTS
    config = _read_config()
    terminology = config.get("terminology") or {}
    ignored = {(_normalize(row.get("alias")), _normalize(row.get("canonical")))
               for row in _list(terminology.get("ignored_alias_suggestions")) if isinstance(row, dict)}
    known = set()
    for row in _list(terminology.get("glossary_list")):
        if not isinstance(row, dict):
            continue
        known.add(_normalize(row.get("original")))
        aliases = row.get("aliases") or []
        if isinstance(aliases, str):
            aliases = re.split(r"[,，、;；\n]+", aliases)
        known.update(_normalize(alias) for alias in _list(aliases))
    for variants in PRESET_ASR_VARIANTS.values():
        for aliases in variants.values():
            known.update(_normalize(alias) for alias in aliases)
    try:
        payload = json.loads(suggestions_path().read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            payload = {}
    except (OSError, ValueError):
        payload = {}
    result = []
    for record in _list(payload.get("records")):
        if not isinstance(record, dict):
            continue
        alias, canonical = record.get("alias"), record.get("canonical")
        if not isinstance(alias, str) or not isinstance(canonical, str):
            continue
        try:
            count, score = int(record.get("count", 0)), float(record.get("best_score", 0))
        except (TypeError, ValueError, OverflowError):
            continue
        if (not math.isfinite(score) or count < 2 or not alias or not canonical or _normalize(alias) in known
                or (_normalize(alias), _normalize(canonical)) in ignored):
            continue
        result.append({"alias": alias, "canonical": canonical, "count": count,
                       "best_score": score, "reading_match": record.get("reading_match"),
                       "examples": [item for item in _list(record.get("examples")) if isinstance(item, str)][:3],
                       "asr_engines": [item for item in _list(record.get("asr_engines")) if isinstance(item, str)],
                       "_last_seen": str(record.get("last_seen", ""))})
    result.sort(key=lambda row: (row["count"], row["_last_seen"], row["best_score"]), reverse=True)
    for row in result:
        row.pop("_last_seen")
    return {"log_enabled": bool(config.get("transcription", {}).get("asr_correction_learning_enabled", False)),
            "reading_enabled": is_installed(), "updated_at": payload.get("updated_at"), "suggestions": result}


@router.get("/alias-suggestions")
async def get_alias_suggestions():
    return await asyncio.to_thread(read_suggestions)


@router.delete("/alias-suggestions")
async def delete_alias_suggestions():
    def clear():
        path = suggestions_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc).isoformat()
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".suggestions-clear-", delete=False) as output:
            temporary = Path(output.name)
            json.dump({"version": 2, "cleared_at": now, "updated_at": now,
                       "records": [], "pending_records": []}, output)
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    await asyncio.to_thread(clear)
    return {"success": True}


@router.get("/reading-addon")
async def get_reading_addon():
    return await asyncio.to_thread(reading_addon_installer.status)


@router.post("/reading-addon/install")
async def install_reading_addon():
    return await asyncio.to_thread(reading_addon_installer.begin)


@router.delete("/reading-addon")
async def delete_reading_addon():
    from backend.core.translator import active_translations
    if any(context.running for context in active_translations.values()):
        raise HTTPException(status_code=409, detail="Stop the running session before removing the reading add-on")
    try:
        return await asyncio.to_thread(reading_addon_installer.remove)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
