"""Download and safely install official llama.cpp Windows runtimes."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.config import settings

RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
_VARIANT_MARKERS = {
    "cpu": "-bin-win-cpu-x64.zip",
    "vulkan": "-bin-win-vulkan-x64.zip",
    "hip": "-bin-win-hip-",
    "cuda12": "-bin-win-cuda-12.",
    "cuda13": "-bin-win-cuda-13.",
}


def llama_root() -> Path:
    exe_dir = getattr(settings, "EXE_DIR", None)
    return (Path(exe_dir) if exe_dir else settings.BASE_DIR.parent) / "llama"


def active_runtime_executable() -> Path | None:
    marker = llama_root() / "active-runtime.txt"
    if not marker.is_file():
        return None
    try:
        relative = marker.read_text(encoding="utf-8").strip()
        candidate = (llama_root() / relative / "llama-server.exe").resolve()
        candidate.relative_to(llama_root().resolve())
        return candidate if candidate.is_file() else None
    except (OSError, ValueError):
        return None


def _release_json() -> dict[str, Any]:
    request = urllib.request.Request(
        RELEASE_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Stream-Translator"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def list_latest_variants(profile: str = "cpu") -> dict[str, Any]:
    release = _release_json()
    assets = release.get("assets", [])
    variants = []
    for variant_id, marker in _VARIANT_MARKERS.items():
        main = next((a for a in assets if marker in str(a.get("name", "")).lower()), None)
        if not main:
            continue
        downloads = [main]
        if variant_id.startswith("cuda"):
            cuda_line = "cuda-12." if variant_id == "cuda12" else "cuda-13."
            cudart = next((a for a in assets if str(a.get("name", "")).lower().startswith("cudart-") and cuda_line in str(a.get("name", "")).lower()), None)
            if cudart:
                downloads.append(cudart)
        recommended = (
            (profile == "cuda" and variant_id == "cuda12")
            or (profile == "rocm" and variant_id == "hip")
            or (profile == "cpu" and variant_id == "cpu")
        )
        variants.append({
            "id": variant_id,
            "label": {"cpu": "Windows x64 CPU", "vulkan": "Windows x64 Vulkan", "hip": "Windows x64 HIP (AMD)", "cuda12": "Windows x64 CUDA 12", "cuda13": "Windows x64 CUDA 13"}[variant_id],
            "recommended": recommended,
            "size": sum(int(a.get("size", 0)) for a in downloads),
            "assets": [{"name": a["name"], "url": a["browser_download_url"]} for a in downloads],
        })
    return {"tag": release.get("tag_name", "latest"), "published_at": release.get("published_at"), "variants": variants}


@dataclass
class InstallStatus:
    state: str = "idle"
    message: str = ""
    progress: float = 0.0
    variant: str = ""
    tag: str = ""
    installed_path: str = ""
    error: str = ""


class LlamaRuntimeInstaller:
    def __init__(self) -> None:
        self._status = InstallStatus()
        self._lock = threading.Lock()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._status)

    def _set(self, **values: Any) -> None:
        with self._lock:
            for key, value in values.items():
                setattr(self._status, key, value)

    async def install(self, variant_id: str, profile: str) -> None:
        if self._status.state in {"resolving", "downloading", "installing"}:
            raise RuntimeError("llama.cpp Runtime 正在下載或安裝")
        self._status = InstallStatus(state="resolving", message="正在讀取官方最新版", variant=variant_id)
        try:
            release = await asyncio.to_thread(list_latest_variants, profile)
            variant = next((item for item in release["variants"] if item["id"] == variant_id), None)
            if not variant:
                raise RuntimeError("官方最新版沒有此 Windows Runtime")
            self._set(tag=release["tag"], state="downloading", message="正在下載官方 Runtime")
            installed = await asyncio.to_thread(self._download_and_install, release["tag"], variant)
            self._set(state="completed", message="llama.cpp Runtime 安裝完成", progress=1.0, installed_path=str(installed))
        except Exception as exc:
            self._set(state="error", message="llama.cpp Runtime 安裝失敗", error=str(exc))

    def _download_and_install(self, tag: str, variant: dict[str, Any]) -> Path:
        root = llama_root()
        root.mkdir(parents=True, exist_ok=True)
        safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in "-._")
        target = root / "runtimes" / f"{safe_tag}-{variant['id']}"
        with tempfile.TemporaryDirectory(prefix="llama-runtime-") as temp_name:
            temp = Path(temp_name)
            extracted = temp / "extracted"
            extracted.mkdir()
            assets = variant["assets"]
            for index, asset in enumerate(assets):
                archive = temp / asset["name"]
                with urllib.request.urlopen(asset["url"], timeout=60) as response, archive.open("wb") as output:
                    total = int(response.headers.get("Content-Length", 0))
                    downloaded = 0
                    while block := response.read(1024 * 1024):
                        output.write(block)
                        downloaded += len(block)
                        portion = downloaded / total if total else 0.5
                        self._set(progress=min(0.8, (index + portion) / len(assets) * 0.8))
                with zipfile.ZipFile(archive) as bundle:
                    for member in bundle.infolist():
                        destination = (extracted / member.filename).resolve()
                        destination.relative_to(extracted.resolve())
                    bundle.extractall(extracted)
            server = next(extracted.rglob("llama-server.exe"), None)
            if not server:
                raise RuntimeError("下載內容缺少 llama-server.exe")
            payload = server.parent
            # CUDA runtime DLLs are published as a separate archive. Merge
            # them beside llama-server.exe regardless of their zip folder.
            for dll in extracted.rglob("*.dll"):
                if dll.parent != payload and not (payload / dll.name).exists():
                    shutil.copy2(dll, payload / dll.name)
            self._set(state="installing", message="正在安裝並驗證 Runtime", progress=0.85)
            staging = target.with_name(target.name + ".installing")
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(payload, staging)
            if not (staging / "llama-server.exe").is_file():
                raise RuntimeError("Runtime 驗證失敗")
            if target.exists():
                shutil.rmtree(target)
            staging.replace(target)
            relative = target.relative_to(root)
            (root / "active-runtime.txt").write_text(str(relative), encoding="utf-8")
        return target / "llama-server.exe"


installer = LlamaRuntimeInstaller()
