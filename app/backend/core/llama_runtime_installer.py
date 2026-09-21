"""Download and safely install official llama.cpp Windows runtimes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import uuid
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.core.external_process import run_external
from backend.core.hardware_detector import GpuDevice, detect_gpus, vram_tier

RELEASE_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
RELEASE_TAG_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases/tags/{tag}"
RECENT_RELEASES_API = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=20"
_VARIANT_LABELS = {
    "cpu": "Windows x64 CPU",
    "vulkan": "Windows x64 Vulkan",
    "hip": "Windows x64 ROCm (AMD)",
    "sycl": "Windows x64 SYCL (Intel Arc)",
    "cuda12": "Windows x64 CUDA 12",
    "cuda13": "Windows x64 CUDA 13",
}
_BUSY_STATES = {"resolving", "downloading", "verifying", "staging", "activating"}


class RuntimeValidationError(RuntimeError):
    """The downloaded native runtime exists but cannot execute on this PC."""

    def __init__(self, message: str, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode


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


def active_runtime_release() -> dict[str, str]:
    """Read the release tag and variant recorded by the atomic installer."""
    marker = llama_root() / "active-runtime.txt"
    if not marker.is_file() or active_runtime_executable() is None:
        return {"tag": "", "variant": ""}
    try:
        relative = marker.read_text(encoding="utf-8").strip().replace("\\", "/")
        directory = Path(relative).name
        match = re.match(r"^(?P<tag>b\d+)-(?P<variant>cuda12|cuda13|hip|sycl|vulkan|cpu)$", directory, re.IGNORECASE)
        if match:
            return {"tag": match.group("tag"), "variant": match.group("variant").lower()}
    except OSError:
        pass
    return {"tag": "", "variant": ""}


def installed_runtime_build_tag() -> str:
    """Read bNNNNN from managed or legacy llama-server version output."""
    candidates = [active_runtime_executable(), llama_root() / "llama-server.exe"]
    for executable in candidates:
        if not executable or not executable.is_file():
            continue
        try:
            result = run_external(
                [str(executable), "--version"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
                check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            output = f"{result.stdout}\n{result.stderr}"
            match = re.search(r"(?:version:\s*|\bb)(\d{3,})\b", output, re.IGNORECASE)
            if match:
                return f"b{match.group(1)}"
        except Exception:
            continue
    return ""


def _fetch_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "Stream-Translator"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def _fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Stream-Translator"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace").strip()


def _release_json() -> dict[str, Any]:
    """Use llama.cpp's official stable pointer before considering raw nightlies.

    The newest bNNNNN build can be published before it has seen broad Windows
    GPU testing.  The stable release's nightly-tag.txt is the upstream-selected
    binary build and is therefore safer for unattended first-run setup.
    """
    try:
        release = _fetch_json(RELEASE_API)
    except Exception:
        release = {}
    if _build_variants(release.get("assets", [])):
        return release
    pointer = next((
        asset for asset in release.get("assets", [])
        if str(asset.get("name") or "").lower() == "nightly-tag.txt"
    ), None)
    if pointer:
        tag = _fetch_text(str(pointer.get("browser_download_url") or "")).strip()
        if not re.fullmatch(r"b\d+", tag, re.IGNORECASE):
            raise RuntimeError("llama.cpp 官方 nightly 指標格式不正確")
        try:
            selected = _fetch_json(RELEASE_TAG_API.format(tag=tag))
            if _build_variants(selected.get("assets", [])):
                return selected
        except Exception:
            pass
    recent = _fetch_json(RECENT_RELEASES_API)
    nightly = [
        item for item in recent if isinstance(item, dict)
        and re.fullmatch(r"b\d+", str(item.get("tag_name") or ""), re.IGNORECASE)
        and _build_variants(item.get("assets", []))
    ] if isinstance(recent, list) else []
    if not nightly:
        raise RuntimeError("找不到可用的 llama.cpp Windows Runtime")
    return max(nightly, key=lambda item: int(str(item["tag_name"])[1:]))


def _asset_digest(asset: dict[str, Any]) -> str:
    digest = str(asset.get("digest") or "").strip().lower()
    return digest if digest.startswith("sha256:") else ""


def _cuda_version_from_name(name: str) -> tuple[int, str] | None:
    """Parse both legacy cuda-12.4 and current cuda-cu12.2.0 asset names."""
    lowered = name.lower()
    patterns = (
        r"(?:cuda[-_])?cu(?P<version>1[23](?:\.\d+(?:\.\d+)?)?)",
        r"cuda[-_](?P<version>1[23](?:\.\d+(?:\.\d+)?)?)",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            version = match.group("version")
            return int(version[:2]), version
    return None


def _is_windows_x64_zip(name: str) -> bool:
    lowered = name.lower()
    return lowered.endswith(".zip") and "-win-" in lowered and "x64" in lowered


def _backend_version_from_name(name: str, backend: str) -> str:
    match = re.search(rf"-{re.escape(backend)}-(\d+(?:\.\d+)*)-x64\.zip$", name.lower())
    return match.group(1) if match else ""


def _asset_payload(asset: dict[str, Any], role: str) -> dict[str, Any]:
    return {
        "name": str(asset.get("name") or ""),
        "url": str(asset.get("browser_download_url") or ""),
        "size": int(asset.get("size") or 0),
        "digest": _asset_digest(asset),
        "role": role,
    }


def _build_variants(assets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build install manifests from official release assets without fixed filenames."""
    mains: dict[str, list[tuple[dict[str, Any], str]]] = {}
    cudart_assets: list[tuple[dict[str, Any], tuple[int, str]]] = []

    for asset in assets:
        name = str(asset.get("name") or "")
        lowered = name.lower()
        if not _is_windows_x64_zip(name):
            continue
        if lowered.startswith("cudart-"):
            cuda_version = _cuda_version_from_name(lowered)
            if cuda_version:
                cudart_assets.append((asset, cuda_version))
            continue
        if not lowered.startswith("llama-") or "-bin-win-" not in lowered:
            continue
        if any(marker in lowered for marker in ("-rpc-", "-server-only-", "-noavx-")):
            continue

        variant_id = ""
        version = ""
        if "-cpu-" in lowered:
            variant_id = "cpu"
        elif "-vulkan-" in lowered:
            variant_id = "vulkan"
        elif "-hip-" in lowered or "-rocm-" in lowered:
            variant_id = "hip"
            version = _backend_version_from_name(lowered, "rocm") or _backend_version_from_name(lowered, "hip")
        elif "-sycl-" in lowered:
            variant_id = "sycl"
        elif "-cuda-" in lowered:
            cuda_version = _cuda_version_from_name(lowered)
            if cuda_version and cuda_version[0] in (12, 13):
                variant_id = f"cuda{cuda_version[0]}"
                version = cuda_version[1]
        if variant_id:
            mains.setdefault(variant_id, []).append((asset, version))

    variants: list[dict[str, Any]] = []
    for variant_id in ("cuda12", "cuda13", "hip", "sycl", "vulkan", "cpu"):
        candidates = mains.get(variant_id, [])
        if not candidates:
            continue
        # Prefer the most specific CUDA version and otherwise a stable name order.
        main, runtime_version = sorted(
            candidates,
            key=lambda item: (item[1], str(item[0].get("name") or "")),
            reverse=True,
        )[0]
        downloads = [_asset_payload(main, "runtime")]
        compatibility_error = ""
        if variant_id.startswith("cuda"):
            dependency = [item for item in cudart_assets if item[1][1] == runtime_version]
            if dependency:
                downloads.append(_asset_payload(dependency[0][0], "dependency"))
            else:
                compatibility_error = "官方 Release 缺少相符的 CUDA Runtime 依賴檔"
        installable = not compatibility_error and all(item["url"] for item in downloads)
        variants.append({
            "id": variant_id,
            "label": _VARIANT_LABELS[variant_id],
            "backend": "cuda" if variant_id.startswith("cuda") else variant_id,
            "runtime_version": runtime_version,
            "recommended": False,
            "installable": installable,
            "compatibility_error": compatibility_error,
            "size": sum(item["size"] for item in downloads),
            "assets": downloads,
        })
    return variants


def _recommend_variant_for_hardware(
    profile: str,
    variants: list[dict[str, Any]],
    devices: list[GpuDevice] | None = None,
) -> tuple[str, str]:
    """Choose a llama.cpp backend independently from the Python package profile.

    The CPU application package can still run a GPU-accelerated llama-server,
    because llama.cpp is an independently downloaded native runtime.  Prefer a
    discrete GPU when one is visible; integrated graphics alone deliberately
    falls back to the CPU build.
    """
    del profile  # llama.cpp is an independent native runtime.
    available = {item["id"] for item in variants if item.get("installable", True)}
    detected = devices if devices is not None else detect_gpus()
    discrete = [device for device in detected if not device.is_integrated]
    selected = max(discrete, key=lambda device: int(device.memory_mb or 0), default=None)
    tier_id, tier_label = vram_tier(selected.memory_mb if selected else None)
    nvidia = bool(selected and (selected.vendor == "nvidia" or selected.backend == "cuda"))
    amd = bool(selected and (selected.vendor == "amd" or selected.backend == "rocm"))
    intel = bool(selected and selected.vendor == "intel" and "arc" in selected.name.lower())

    if nvidia:
        for candidate in ("cuda12", "cuda13", "vulkan"):
            if candidate in available:
                return candidate, f"偵測到 NVIDIA 獨立 GPU（{tier_label}），推薦 CUDA llama runtime。"
    if amd:
        for candidate in ("hip", "vulkan"):
            if candidate in available:
                return candidate, f"偵測到 AMD 獨立 GPU（{tier_label}），推薦 HIP llama runtime。"
    if intel:
        for candidate in ("sycl", "vulkan"):
            if candidate in available:
                return candidate, f"偵測到 Intel Arc（{tier_label}），推薦 SYCL llama runtime。"
    if discrete and "vulkan" in available:
        return "vulkan", "偵測到獨立 GPU，但沒有可用的原生 CUDA/ROCm/SYCL runtime，推薦 Vulkan。"
    if not detected:
        return "", "無法確認本機 GPU，請手動選擇 llama.cpp Runtime。"
    if "cpu" in available:
        return "cpu", "只偵測到內顯，推薦 CPU llama runtime；仍可手動選擇 Vulkan。"
    return "", "沒有可用的 llama.cpp runtime variant。"


def list_latest_variants(
    profile: str = "cpu",
    devices: list[GpuDevice] | None = None,
) -> dict[str, Any]:
    release = _release_json()
    assets = release.get("assets", [])
    variants = _build_variants(assets)
    latest_tag = str(release.get("tag_name") or "latest")
    installed = active_runtime_release()
    if not installed["tag"]:
        installed["tag"] = installed_runtime_build_tag()
    is_latest = bool(installed["tag"] and installed["tag"].lower() == latest_tag.lower())
    detected_devices = devices if devices is not None else detect_gpus()
    recommended_variant, recommendation_reason = _recommend_variant_for_hardware(profile, variants, detected_devices)
    for variant in variants:
        variant["recommended"] = variant["id"] == recommended_variant
        variant["installed"] = variant["id"] == installed["variant"]
        variant["installed_latest"] = is_latest and variant["installed"]
    return {
        "source": "github",
        "tag": latest_tag,
        "installed_tag": installed["tag"],
        "installed_variant": installed["variant"],
        "is_latest": is_latest,
        "published_at": release.get("published_at"),
        "recommended_variant": recommended_variant,
        "recommendation_reason": recommendation_reason,
        "detected_gpus": [
            {"name": device.name, "vendor": device.vendor, "backend": device.backend,
             "memory_mb": device.memory_mb, "is_integrated": device.is_integrated}
            for device in detected_devices
        ],
        "variants": variants,
    }


@dataclass
class FileInstallStatus:
    name: str
    role: str = "runtime"
    state: str = "pending"
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    sha256: str = ""
    error: str = ""


@dataclass
class InstallStatus:
    state: str = "idle"
    message: str = ""
    progress: float = 0.0
    job_id: str = ""
    variant: str = ""
    tag: str = ""
    installed_path: str = ""
    previous_runtime: str = ""
    error: str = ""
    fallback_reason: str = ""
    files: list[dict[str, Any]] | None = None


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

    def begin(self, variant_id: str) -> str:
        with self._lock:
            if self._status.state in _BUSY_STATES:
                raise RuntimeError("llama.cpp Runtime 正在下載或安裝")
            job_id = uuid.uuid4().hex
            self._status = InstallStatus(
                state="resolving",
                message="正在讀取官方最新版",
                job_id=job_id,
                variant=variant_id,
                files=[],
            )
        return job_id

    async def install(self, job_id: str, variant_id: str, profile: str) -> None:
        try:
            # Hardware recommendation was already shown by the release endpoint;
            # installation only needs a fresh official manifest.
            release = await asyncio.to_thread(list_latest_variants, profile, [])
            variant = next((item for item in release["variants"] if item["id"] == variant_id), None)
            if not variant:
                raise RuntimeError("官方最新版沒有此 Windows Runtime")
            if not variant.get("installable", True):
                raise RuntimeError(variant.get("compatibility_error") or "此 Runtime 資產不完整")
            if self.status().get("job_id") != job_id:
                return
            self._prepare_variant_status(release["tag"], variant)
            try:
                installed = await asyncio.to_thread(self._download_and_install, release["tag"], variant)
                completed_message = "llama.cpp Runtime 安裝完成"
            except RuntimeValidationError as validation_error:
                fallback = next((item for item in release["variants"] if item["id"] == "vulkan" and item.get("installable", True)), None)
                if not fallback or variant_id not in {"cuda12", "cuda13", "hip", "sycl"}:
                    raise
                reason = f"{variant['label']} 無法在此電腦執行（{validation_error}），已改用 Vulkan GPU Runtime。"
                self._prepare_variant_status(release["tag"], fallback, fallback_reason=reason)
                installed = await asyncio.to_thread(self._download_and_install, release["tag"], fallback)
                completed_message = "原生 GPU Runtime 驗證失敗，已改用 Vulkan GPU Runtime"
            self._set(state="completed", message=completed_message, progress=1.0, installed_path=str(installed))
        except Exception as exc:
            self._set(state="error", message="llama.cpp Runtime 安裝失敗", error=str(exc))

    def _prepare_variant_status(self, tag: str, variant: dict[str, Any], fallback_reason: str = "") -> None:
        files = [
            asdict(FileInstallStatus(
                name=item["name"], role=item.get("role", "runtime"),
                total_bytes=int(item.get("size") or 0),
            ))
            for item in variant["assets"]
        ]
        self._set(
            tag=tag, variant=variant["id"], state="downloading", progress=0.0,
            message="正在下載官方 Runtime", files=files,
            fallback_reason=fallback_reason, error="",
        )

    def _set_file(self, index: int, **values: Any) -> None:
        with self._lock:
            files = list(self._status.files or [])
            if index >= len(files):
                return
            updated = dict(files[index])
            updated.update(values)
            files[index] = updated
            self._status.files = files

    @staticmethod
    def _safe_extract(bundle: zipfile.ZipFile, destination: Path) -> None:
        root = destination.resolve()
        for member in bundle.infolist():
            member_path = (destination / member.filename).resolve()
            try:
                member_path.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"Runtime ZIP 含有不安全路徑：{member.filename}") from exc
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                raise RuntimeError(f"Runtime ZIP 含有不允許的符號連結：{member.filename}")
        bad_member = bundle.testzip()
        if bad_member:
            raise RuntimeError(f"Runtime ZIP 損壞：{bad_member}")
        bundle.extractall(destination)

    @staticmethod
    def _validate_runtime(directory: Path) -> Path:
        server = directory / "llama-server.exe"
        if not server.is_file():
            raise RuntimeValidationError("Runtime 驗證失敗：缺少 llama-server.exe")
        result = run_external(
            [str(server), "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            output = (result.stdout + "\n" + result.stderr).strip()
            unsigned_code = result.returncode & 0xFFFFFFFF
            detail = output or f"{unsigned_code} (0x{unsigned_code:08X})"
            raise RuntimeValidationError(f"llama-server.exe 驗證失敗：{detail}", result.returncode)
        return server

    @staticmethod
    def _write_active_marker(root: Path, relative: Path) -> None:
        marker = root / "active-runtime.txt"
        temporary = marker.with_suffix(".txt.tmp")
        temporary.write_text(str(relative), encoding="utf-8")
        os.replace(temporary, marker)

    def _download_and_install(self, tag: str, variant: dict[str, Any]) -> Path:
        root = llama_root()
        root.mkdir(parents=True, exist_ok=True)
        safe_tag = "".join(ch for ch in tag if ch.isalnum() or ch in "-._")
        target = root / "runtimes" / f"{safe_tag}-{variant['id']}"
        marker = root / "active-runtime.txt"
        previous_runtime = marker.read_text(encoding="utf-8").strip() if marker.is_file() else ""
        self._set(previous_runtime=previous_runtime)
        with tempfile.TemporaryDirectory(prefix="llama-runtime-") as temp_name:
            temp = Path(temp_name)
            extracted = temp / "extracted"
            extracted.mkdir()
            assets = variant["assets"]
            for index, asset in enumerate(assets):
                asset_name = str(asset["name"])
                if Path(asset_name).name != asset_name:
                    raise RuntimeError(f"官方資產名稱不安全：{asset_name}")
                archive = temp / asset_name
                sha256 = ""
                self._set_file(index, state="downloading", progress=0.0, error="")
                try:
                    with urllib.request.urlopen(asset["url"], timeout=60) as response, archive.open("wb") as output:
                        total = int(response.headers.get("Content-Length", 0)) or int(asset.get("size") or 0)
                        downloaded = 0
                        digest = hashlib.sha256()
                        while block := response.read(1024 * 1024):
                            output.write(block)
                            digest.update(block)
                            downloaded += len(block)
                            portion = downloaded / total if total else 0.5
                            self._set_file(
                                index,
                                progress=min(1.0, portion),
                                downloaded_bytes=downloaded,
                                total_bytes=total,
                            )
                            self._set(progress=min(0.7, (index + portion) / len(assets) * 0.7))
                    sha256 = digest.hexdigest()
                    expected = str(asset.get("digest") or "").lower()
                    if expected and expected != f"sha256:{sha256}":
                        raise RuntimeError("SHA-256 驗證失敗")
                    self._set_file(index, state="verifying", progress=1.0, sha256=sha256)
                    with zipfile.ZipFile(archive) as bundle:
                        self._safe_extract(bundle, extracted)
                    self._set_file(index, state="completed", progress=1.0, sha256=sha256)
                except Exception as exc:
                    self._set_file(index, state="error", error=str(exc), sha256=sha256)
                    raise RuntimeError(f"{asset['name']}：{exc}") from exc
            self._set(state="verifying", message="正在驗證 Runtime 檔案", progress=0.75)
            server = next(extracted.rglob("llama-server.exe"), None)
            if not server:
                raise RuntimeError("下載內容缺少 llama-server.exe")
            payload = server.parent
            # CUDA runtime DLLs are published as a separate archive. Merge
            # them beside llama-server.exe regardless of their zip folder.
            for dll in extracted.rglob("*.dll"):
                if dll.parent != payload and not (payload / dll.name).exists():
                    shutil.copy2(dll, payload / dll.name)
            self._set(state="staging", message="正在建立 Runtime 暫存版本", progress=0.82)
            staging = target.with_name(target.name + f".installing-{self._status.job_id[:8]}")
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(payload, staging)
            try:
                self._validate_runtime(staging)
            except Exception:
                shutil.rmtree(staging, ignore_errors=True)
                raise
            self._set(state="activating", message="正在啟用新的 Runtime", progress=0.95)
            backup = target.with_name(target.name + f".backup-{self._status.job_id[:8]}")
            moved_existing = False
            try:
                if backup.exists():
                    shutil.rmtree(backup)
                if target.exists():
                    target.replace(backup)
                    moved_existing = True
                staging.replace(target)
                relative = target.relative_to(root)
                self._write_active_marker(root, relative)
            except Exception:
                if target.exists():
                    shutil.rmtree(target)
                if moved_existing and backup.exists():
                    backup.replace(target)
                if previous_runtime:
                    self._write_active_marker(root, Path(previous_runtime))
                elif marker.exists():
                    marker.unlink()
                raise
            finally:
                if staging.exists():
                    shutil.rmtree(staging)
            if backup.exists():
                shutil.rmtree(backup)
        return target / "llama-server.exe"


installer = LlamaRuntimeInstaller()
