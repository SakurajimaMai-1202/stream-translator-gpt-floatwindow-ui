"""Lightweight runtime selection and CPU model compatibility checks."""

import os
import sys
from pathlib import Path

from backend.config import settings

HAAS_MODEL_ID = "oboroge0/Haas-ja-v1.0-onnx-quantized"


def runtime_contains_model(runtime: Path, model_id: str) -> bool:
    registry = Path(runtime) / "Lib/site-packages/stream_translator_gpt/sherpa_onnx_models.py"
    try:
        return model_id in registry.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False


def haas_runtime_update_message(profile: str | None) -> str:
    if (profile or "").strip().lower() == "cpu":
        return "目前的 CPU 執行環境版本過舊，不支援 Haas。請下載完整安裝包更新後再試。"
    return "目前安裝的 CPU ASR Runtime 版本過舊，不支援 Haas。請到「ASR 模型管理」重新安裝 CPU ASR Runtime 後再試。"


def resolve_profile_python(runtime_profile: str | None, asr_compute_backend: str | None = None) -> str | None:
    profile = (runtime_profile or "").strip().lower()
    compute = (asr_compute_backend or "auto").strip().lower()
    candidates: list[Path] = []
    if getattr(sys, 'frozen', False):
        if compute == 'cpu':
            runtime_name = '_runtime' if profile == 'cpu' else '_runtime_cpu_asr'
            candidates.append(Path(sys.executable).parent / runtime_name / 'python.exe')
        else:
            candidates.append(Path(sys.executable).parent / '_runtime' / 'python.exe')
    if compute == 'cpu':
        candidates.append(settings.BASE_DIR / 'build-runtime-cache' / 'cpu-runtime' / 'python.exe')
    elif profile:
        candidates.append(settings.BASE_DIR / 'build-runtime-cache' / f'{profile}-runtime' / 'python.exe')
    env_python = os.environ.get('STREAM_TRANSLATOR_BUILD_PYTHON')
    if env_python:
        candidates.append(Path(env_python))

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None

