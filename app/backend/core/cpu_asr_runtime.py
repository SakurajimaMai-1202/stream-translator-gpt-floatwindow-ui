"""Lightweight runtime selection and CPU model compatibility checks."""

import hashlib
import os
import sys
from pathlib import Path

from backend.config import settings

HAAS_MODEL_ID = "oboroge0/Haas-ja-v1.0-onnx-quantized"

_engine_fingerprints: dict[Path, tuple[tuple, str]] = {}


def engine_fingerprint(site_packages_engine_dir: Path) -> str | None:
    """Hash package contents, reusing the digest while file metadata is unchanged."""
    root = Path(site_packages_engine_dir).resolve()
    if not root.is_dir():
        _engine_fingerprints.pop(root, None)
        return None
    files = []
    try:
        for directory, directories, names in os.walk(root):
            directories[:] = [name for name in directories if name != '__pycache__']
            for name in names:
                if not name.endswith('.pyc'):
                    path = Path(directory) / name
                    files.append((path.relative_to(root).as_posix(), path, path.stat()))
    except OSError:
        # An install, restore or antivirus lock can race the scan.
        return None
    files.sort(key=lambda item: item[0])
    key = (root, tuple((relative, stat.st_size, stat.st_mtime_ns) for relative, _, stat in files))
    cached = _engine_fingerprints.get(root)
    if cached and cached[0] == key:
        return cached[1]
    digest = hashlib.sha256()
    try:
        for relative, path, _stat in files:
            digest.update(relative.encode('utf-8') + b'\0')
            # Only Python source is compared by content: rebuilt DLLs embed a
            # link timestamp, and checkouts may differ in line endings. Other
            # files still count by name, so a missing module or DLL shows up.
            if relative.endswith('.py'):
                digest.update(path.read_bytes().replace(b'\r\n', b'\n'))
            digest.update(b'\0')
    except OSError:
        return None
    result = digest.hexdigest()
    _engine_fingerprints[root] = (key, result)
    return result


def sidecar_engine_mismatch_message(runtime_profile: str | None,
                                    asr_compute_backend: str | None) -> str | None:
    if (not getattr(sys, 'frozen', False)
            or (asr_compute_backend or '').strip().lower() != 'cpu'
            or (runtime_profile or '').strip().lower() == 'cpu'):
        return None
    root = Path(sys.executable).parent
    python = resolve_profile_python(runtime_profile, asr_compute_backend)
    if not python or Path(python).resolve() != (root / '_runtime_cpu_asr/python.exe').resolve():
        return None
    package = Path('Lib/site-packages/stream_translator_gpt')
    main = engine_fingerprint(root / '_runtime' / package)
    if main is not None and main != engine_fingerprint(root / '_runtime_cpu_asr' / package):
        return 'CPU ASR Runtime 內的翻譯引擎與主程式版本不一致，請到「ASR 模型管理」重新安裝 CPU ASR Runtime 後再試。'
    return None


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


def cpu_asr_start_update_message(cli_args: dict) -> str | None:
    """Return the required runtime update message before starting packaged Haas."""
    if (not getattr(sys, 'frozen', False)
            or str(cli_args.get('asr_compute_backend') or 'auto').lower() != 'cpu'
            or not cli_args.get('use_nemo_asr')
            or cli_args.get('nemo_asr_model') != HAAS_MODEL_ID):
        return None
    profile_python = resolve_profile_python(
        str(cli_args.get('runtime_profile') or ''),
        str(cli_args.get('asr_compute_backend') or 'auto'),
    )
    if profile_python and not runtime_contains_model(Path(profile_python).parent, HAAS_MODEL_ID):
        return haas_runtime_update_message(cli_args.get('runtime_profile'))
    return None
