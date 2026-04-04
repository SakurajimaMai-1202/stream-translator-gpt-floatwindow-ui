"""系統相依套件檢查工具。"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional

from backend.config import settings

_CACHE_TTL_SECONDS = 30
_cached_result: Optional[Dict] = None
_cached_at: float = 0.0


def _candidate_ffmpeg_paths() -> list[Path]:
    """回傳可能的 ffmpeg.exe 路徑候選清單。"""
    candidates: list[Path] = []

    # 1) PATH 中可找到的 ffmpeg
    ffmpeg_in_path = shutil.which("ffmpeg")
    if ffmpeg_in_path:
        candidates.append(Path(ffmpeg_in_path))

    # 2) 打包輸出常見位置：執行檔同層 ffmpeg/bin/ffmpeg.exe
    if getattr(os, "name", "") == "nt":
        exe_dir = getattr(settings, "EXE_DIR", None)
        if exe_dir:
            candidates.append(Path(exe_dir) / "ffmpeg" / "bin" / "ffmpeg.exe")

    # 3) 開發環境常見位置：專案根目錄/ffmpeg-8.1-essentials_build/.../bin/ffmpeg.exe
    # settings.BASE_DIR 在開發模式為 ui2 根目錄，parent 為專案根目錄
    project_root = settings.BASE_DIR.parent
    candidates.append(
        project_root
        / "ffmpeg-8.1-essentials_build"
        / "ffmpeg-8.1-essentials_build"
        / "bin"
        / "ffmpeg.exe"
    )

    # 4) ui2 目錄內的 ffmpeg/bin（給部分手動佈署場景）
    candidates.append(settings.BASE_DIR / "ffmpeg" / "bin" / "ffmpeg.exe")

    # 去重並保序
    unique: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        key = str(item).lower()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def _read_ffmpeg_version(ffmpeg_path: Path) -> Optional[str]:
    """執行 ffmpeg -version 並解析版本字串。"""
    try:
        result = subprocess.run(
            [str(ffmpeg_path), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            return None

        first_line = (result.stdout or "").splitlines()[0] if result.stdout else ""
        # 典型格式: ffmpeg version 8.1-essentials_build-www.gyan.dev ...
        if first_line.lower().startswith("ffmpeg version"):
            return first_line.replace("ffmpeg version", "", 1).strip()
        return first_line.strip() or None
    except Exception:
        return None


def check_ffmpeg(force_refresh: bool = False) -> Dict:
    """檢查 ffmpeg 是否可用，並回傳版本/路徑資訊。"""
    global _cached_result, _cached_at

    now = time.time()
    if not force_refresh and _cached_result is not None and (now - _cached_at) < _CACHE_TTL_SECONDS:
        return _cached_result

    for candidate in _candidate_ffmpeg_paths():
        if candidate.exists():
            version = _read_ffmpeg_version(candidate)
            _cached_result = {
                "available": version is not None,
                "path": str(candidate),
                "version": version,
                "checked_at": int(now),
            }
            _cached_at = now
            return _cached_result

    _cached_result = {
        "available": False,
        "path": None,
        "version": None,
        "checked_at": int(now),
    }
    _cached_at = now
    return _cached_result
