"""Download and safely install the optional sherpa-onnx CPU ASR runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import urllib.error
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.core.portable_paths import get_app_root, get_cpu_asr_runtime_path


REPOSITORY = "SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui"
ASSET_TEMPLATE = "StreamTranslator-CPU-ASR-Sidecar-v{version}.zip"


@dataclass
class SidecarInstallState:
    status: str = "idle"
    progress: float = 0.0
    message: str = ""
    error: str = ""
    bytes_downloaded: int = 0
    bytes_total: int = 0
    asset_url: str = ""
    restart_required: bool = False
    healthy: bool = False
    health_error: str = ""


class CpuAsrSidecarManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = SidecarInstallState()
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._health_fingerprint: tuple[object, ...] | None = None
        self._health_result: tuple[bool, str] = (False, "CPU ASR runtime is not installed")

    def status(self) -> dict[str, Any]:
        with self._lock:
            state = asdict(self._state)
        runtime = get_cpu_asr_runtime_path()
        healthy, health_error = self._runtime_health(runtime)
        state.update({
            "installed": (runtime / "python.exe").is_file(),
            "healthy": healthy,
            "health_error": health_error,
            "runtime_path": str(runtime),
            "version": self._version(),
            "asset_name": self._asset_name(),
        })
        return state

    def start(self, *, asset_url: str | None = None, sha256_url: str | None = None) -> dict[str, Any]:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return asdict(self._state)
            resolved_asset = asset_url or self._default_asset_url()
            resolved_sha = sha256_url or f"{resolved_asset}.sha256"
            self._cancel.clear()
            self._state = SidecarInstallState(
                status="starting", message="Preparing CPU ASR sidecar download", asset_url=resolved_asset
            )
            self._worker = threading.Thread(
                target=self._run,
                kwargs={"asset_url": resolved_asset, "sha256_url": resolved_sha},
                daemon=True,
                name="cpu-asr-sidecar-installer",
            )
            self._worker.start()
        return self.status()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if self._worker is not None and self._worker.is_alive() and self._state.status != "installing":
                self._cancel.set()
                self._state.message = "Cancelling CPU ASR runtime download"
        return self.status()

    def _set(self, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(self._state, key, value)

    def _version(self) -> str:
        manifest = get_app_root() / "_runtime" / "runtime-version.json"
        try:
            version = str(json.loads(manifest.read_text(encoding="utf-8")).get("app_version") or "")
        except (OSError, ValueError, TypeError):
            version = ""
        return version or settings.APP_VERSION

    def _asset_name(self) -> str:
        return ASSET_TEMPLATE.format(version=self._version())

    def _default_asset_url(self) -> str:
        override = os.environ.get("STREAM_TRANSLATOR_CPU_ASR_SIDECAR_URL", "").strip()
        if override:
            return override
        version = self._version()
        return f"https://github.com/{REPOSITORY}/releases/download/v{version}/{self._asset_name()}"

    @staticmethod
    def _open_url(url: str, *, headers: dict[str, str] | None = None):
        local = Path(os.path.expandvars(os.path.expanduser(url)))
        if local.is_file():
            return local.open("rb")
        request_headers = {"User-Agent": "StreamTranslator-CPU-ASR-Installer"}
        request_headers.update(headers or {})
        request = urllib.request.Request(url, headers=request_headers)
        return urllib.request.urlopen(request, timeout=60)

    def _download(self, url: str, destination: Path) -> None:
        self._set(status="downloading", message="Downloading CPU ASR runtime")
        existing = destination.stat().st_size if destination.is_file() else 0
        local = Path(os.path.expandvars(os.path.expanduser(url)))
        request_headers = {"Range": f"bytes={existing}-"} if existing and not local.is_file() else None
        try:
            response = self._open_url(url, headers=request_headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and existing:
                self._set(bytes_downloaded=existing, bytes_total=existing, progress=0.75)
                return
            raise
        with response:
            response_status = getattr(response, "status", None)
            resumed = existing > 0 and (local.is_file() or response_status == 206)
            if resumed and local.is_file():
                source_size = local.stat().st_size
                if existing > source_size:
                    resumed = False
                else:
                    response.seek(existing)
            downloaded = existing if resumed else 0
            content_length = int(getattr(response, "headers", {}).get("Content-Length", 0) or 0)
            total = downloaded + content_length if content_length else 0
            mode = "ab" if resumed else "wb"
            if resumed:
                self._set(message="Resuming CPU ASR runtime download")
            with destination.open(mode) as output:
                while True:
                    self._raise_if_cancelled()
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    downloaded += len(block)
                    self._set(
                        bytes_downloaded=downloaded,
                        bytes_total=total,
                        progress=(downloaded / total * 0.75) if total else 0.25,
                    )

    def _expected_sha256(self, url: str) -> str:
        with self._open_url(url) as response:
            text = response.read().decode("utf-8", errors="replace").strip()
        digest = text.split()[0].lower() if text else ""
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise RuntimeError("CPU ASR sidecar SHA-256 file is invalid")
        return digest

    @staticmethod
    def _runtime_fingerprint(runtime: Path) -> tuple[object, ...]:
        result: list[object] = [str(runtime)]
        for path in (runtime / "python.exe", runtime / "runtime-version.json"):
            try:
                stat = path.stat()
                result.extend((stat.st_size, stat.st_mtime_ns))
            except OSError:
                result.extend((None, None))
        return tuple(result)

    def _runtime_health(self, runtime: Path) -> tuple[bool, str]:
        fingerprint = self._runtime_fingerprint(runtime)
        with self._lock:
            if fingerprint == self._health_fingerprint:
                return self._health_result
        try:
            self._validate_runtime(runtime)
            result = (True, "")
        except Exception as exc:
            result = (False, str(exc))
        with self._lock:
            self._health_fingerprint = fingerprint
            self._health_result = result
        return result

    def _invalidate_health(self) -> None:
        with self._lock:
            self._health_fingerprint = None

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise InterruptedError("CPU ASR sidecar installation cancelled")

    def _sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            while True:
                self._raise_if_cancelled()
                block = stream.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        root = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                target = (root / item.filename).resolve()
                if target != root and root not in target.parents:
                    raise RuntimeError(f"Unsafe path in sidecar archive: {item.filename}")
            bundle.extractall(root)

    @staticmethod
    def _validate_runtime(runtime: Path) -> None:
        python = runtime / "python.exe"
        manifest_path = runtime / "runtime-version.json"
        if not python.is_file() or not manifest_path.is_file():
            raise RuntimeError("CPU ASR sidecar is missing python.exe or runtime-version.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("profile") != "cpu" or manifest.get("torch_backend") != "none":
            raise RuntimeError("CPU ASR sidecar manifest has an unexpected runtime profile")
        if not manifest.get("sherpa_onnx"):
            raise RuntimeError("CPU ASR sidecar manifest does not declare sherpa-onnx")
        result = subprocess.run(
            [
                str(python), "-I", "-c",
                "import glob, pathlib, sherpa_onnx, stream_translator_gpt.main, sys; "
                "from pathlib import Path; root=Path(sys.executable).resolve().parent; "
                "paths=[Path(pathlib.__file__).resolve(), Path(glob.__file__).resolve()]; "
                "assert all(root == p.parent or root in p.parents for p in paths), paths; "
                "print(sherpa_onnx.__version__)",
            ],
            cwd=str(runtime), capture_output=True, text=True, timeout=90,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode != 0:
            raise RuntimeError(f"CPU ASR sidecar import validation failed: {result.stderr[-500:]}")

    def _install(self, extracted: Path) -> None:
        runtime = extracted
        nested = extracted / "_runtime_cpu_asr"
        if nested.is_dir():
            runtime = nested
        self._validate_runtime(runtime)

        target = get_cpu_asr_runtime_path()
        if target.name == "_runtime":
            raise RuntimeError("The CPU package already contains its CPU ASR runtime")
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = target.with_name(f"{target.name}.backup")
        staging = target.with_name(f"{target.name}.staging")
        if backup.exists():
            shutil.rmtree(backup)
        self._invalidate_health()
        if staging.exists():
            shutil.rmtree(staging)
        shutil.copytree(runtime, staging)
        self._validate_runtime(staging)
        if target.exists():
            target.replace(backup)
        try:
            staging.replace(target)
            self._validate_runtime(target)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                backup.replace(target)
            raise
        if backup.exists():
            shutil.rmtree(backup)
        self._invalidate_health()

    def _run(self, *, asset_url: str, sha256_url: str) -> None:
        try:
            download_dir = get_cpu_asr_runtime_path().parent / ".downloads"
            download_dir.mkdir(parents=True, exist_ok=True)
            archive = download_dir / f"{self._asset_name()}.part"
            with tempfile.TemporaryDirectory(prefix="stream-translator-cpu-asr-") as temporary:
                temp = Path(temporary)
                self._download(asset_url, archive)
                self._raise_if_cancelled()
                self._set(status="verifying", message="Verifying SHA-256", progress=0.78)
                expected = self._expected_sha256(sha256_url)
                actual = self._sha256(archive)
                if actual != expected:
                    archive.unlink(missing_ok=True)
                    raise RuntimeError(f"CPU ASR sidecar SHA-256 mismatch: expected {expected}, got {actual}")
                extracted = temp / "extracted"
                extracted.mkdir()
                self._raise_if_cancelled()
                self._set(status="installing", message="Installing isolated CPU ASR runtime", progress=0.82)
                self._safe_extract(archive, extracted)
                self._install(extracted)
            archive.unlink(missing_ok=True)
            self._set(
                status="completed", progress=1.0, message="CPU ASR runtime installed",
                error="", restart_required=True,
            )
        except InterruptedError:
            self._set(status="cancelled", message="CPU ASR runtime installation cancelled", error="")
        except Exception as exc:
            self._set(status="error", message="CPU ASR runtime installation failed", error=str(exc))


cpu_asr_sidecar_manager = CpuAsrSidecarManager()
