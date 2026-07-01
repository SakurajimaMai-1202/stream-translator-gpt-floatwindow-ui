"""Resolve portable application data paths shared by the UI and ASR runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping

import yaml

from backend.config import settings


def get_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return settings.BASE_DIR.resolve()


def get_model_storage_root() -> Path:
    configured = ""
    try:
        if settings.CONFIG_FILE.exists():
            with open(settings.CONFIG_FILE, "r", encoding="utf-8") as config_file:
                config = yaml.safe_load(config_file) or {}
            configured = str(config.get("models", {}).get("storage_path", "") or "").strip()
    except (OSError, yaml.YAMLError):
        configured = ""

    if configured:
        path = Path(os.path.expandvars(os.path.expanduser(configured)))
        if not path.is_absolute():
            path = get_app_root() / path
        return path.resolve()

    return (get_app_root() / "models" / "huggingface").resolve()


def get_huggingface_hub_cache() -> Path:
    return get_model_storage_root() / "hub"


def get_modelscope_cache() -> Path:
    return get_model_storage_root() / "modelscope"


def ensure_model_storage() -> Path:
    root = get_model_storage_root()
    (root / "hub").mkdir(parents=True, exist_ok=True)
    (root / "modelscope").mkdir(parents=True, exist_ok=True)
    return root


def apply_model_cache_environment(env: Mapping[str, str] | None = None) -> dict[str, str]:
    result = dict(env or os.environ)
    root = ensure_model_storage()
    result["HF_HOME"] = str(root)
    result["HUGGINGFACE_HUB_CACHE"] = str(root / "hub")
    result["TRANSFORMERS_CACHE"] = str(root / "hub")
    result["MODELSCOPE_CACHE"] = str(root / "modelscope")
    return result
