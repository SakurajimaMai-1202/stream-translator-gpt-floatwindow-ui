"""Check, download, verify, and stage profile-matched application updates."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.core.portable_paths import get_app_root, get_packaged_runtime_profile


REPOSITORY = "SakurajimaMai-1202/stream-translator-gpt-floatwindow-ui"
RELEASE_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
ASSET_NAMES = {
    "cuda": "StreamTranslator-CUDA-App-Update.zip",
    "cpu": "StreamTranslator-CPU-App-Update.zip",
    "rocm": "StreamTranslator-ROCm-Experimental-App-Update.zip",
}
MINIMUM_DIRECT_UPDATE_VERSION = "1.3.11"
UPDATE_MODES = {"app_only", "runtime_replace"}
ALLOWED_UPDATE_NAMES = {
    "app-update-build.json", "StreamTranslatorUpdater.exe", "diagnose_runtime.ps1",
    "PORTABLE_GUIDE_zh-TW.txt", "smoke_sensevoice_asr.ps1", "Stream Translator.exe",
    "UPDATE_NOTES_zh-TW.txt", "_internal", "_js_runtime", "_runtime",
}


@dataclass
class AppUpdateState:
    status: str = "idle"
    progress: float = 0.0
    message: str = ""
    error: str = ""
    current_version: str = ""
    latest_version: str = ""
    profile: str = ""
    available: bool = False
    asset_name: str = ""
    asset_url: str = ""
    asset_size: int = 0
    bytes_downloaded: int = 0
    bytes_total: int = 0
    release_url: str = ""
    release_notes: str = ""
    ready_to_apply: bool = False
    minimum_upgradable_version: str = ""
    requires_full_install: bool = False
    update_mode: str = "app_only"


class AppUpdateManager:
    def __init__(self) -> None:
        self._cleanup_previous_backup()
        profile = get_packaged_runtime_profile() or ""
        self._state = AppUpdateState(
            current_version=self._current_version(), profile=profile,
            asset_name=ASSET_NAMES.get(profile, ""),
        )
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._expected_digest = ""
        self._assets: list[dict[str, Any]] = []
        self._archive: Path | None = None
        self._staging: Path | None = None

    @staticmethod
    def _cleanup_previous_backup() -> None:
        app_root = get_app_root().resolve()
        result_path = app_root / ".app-update" / "update-result.json"
        try:
            result = json.loads(result_path.read_text(encoding="utf-8-sig"))
            backup = Path(str(result.get("backup") or "")).resolve()
            if (
                result.get("status") == "completed"
                and backup.is_dir()
                and backup.parent == app_root.parent
                and backup.name.startswith(".stream-translator-backup-")
            ):
                shutil.rmtree(backup)
                result_path.unlink(missing_ok=True)
        except (OSError, ValueError, TypeError):
            pass

    def _current_version(self) -> str:
        # The runtime manifest describes the packaged Python/GPU runtime.  It
        # can legitimately remain older after an app-only update, so using its
        # app_version here causes an already-updated UI/backend to offer the
        # same release again.  The running backend is the authoritative source
        # for the application version.
        return str(settings.APP_VERSION)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._state)

    def _set(self, **changes: Any) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(self._state, key, value)

    @staticmethod
    def _version_tuple(value: str) -> tuple[int, ...]:
        parts = value.strip().lstrip("v").split(".")
        return tuple(int("".join(char for char in part if char.isdigit()) or 0) for part in parts)

    @staticmethod
    def _open_url(url: str, *, headers: dict[str, str] | None = None):
        local = Path(os.path.expandvars(os.path.expanduser(url)))
        if local.is_file():
            return local.open("rb")
        request_headers = {"User-Agent": "StreamTranslator-App-Updater"}
        request_headers.update(headers or {})
        return urllib.request.urlopen(urllib.request.Request(url, headers=request_headers), timeout=60)

    def check(self, *, release_api: str | None = None) -> dict[str, Any]:
        profile = self._state.profile
        if profile not in ASSET_NAMES:
            self._set(status="unsupported", error="App updates are available only in packaged CPU/CUDA/ROCm builds")
            return self.status()
        api = release_api or os.environ.get("STREAM_TRANSLATOR_UPDATE_RELEASE_API", "").strip() or RELEASE_API
        self._set(status="checking", message="Checking GitHub Releases", error="")
        try:
            with self._open_url(api) as response:
                release = json.loads(response.read().decode("utf-8"))
            latest = str(release.get("tag_name") or "").lstrip("v")
            asset_name = ASSET_NAMES[profile]
            release_assets = list(release.get("assets", []))
            asset = next((item for item in release_assets if item.get("name") == asset_name), None)
            parts = sorted(
                (item for item in release_assets if str(item.get("name") or "").startswith(asset_name + ".part")),
                key=lambda item: str(item.get("name") or ""),
            )
            selected_assets = [asset] if asset else parts
            if not latest or not selected_assets:
                raise RuntimeError(f"Release does not contain {asset_name}")
            if any(not str(item.get("digest") or "").startswith("sha256:") for item in selected_assets):
                raise RuntimeError("GitHub Release update asset does not provide SHA-256 digests")
            self._assets = selected_assets
            self._expected_digest = str(asset.get("digest") or "").removeprefix("sha256:").lower() if asset else ""
            available = self._version_tuple(latest) > self._version_tuple(self._state.current_version)
            requires_full = available and self._version_tuple(self._state.current_version) < self._version_tuple(MINIMUM_DIRECT_UPDATE_VERSION)
            self._set(
                status="full_install_required" if requires_full else ("available" if available else "up_to_date"),
                available=available and not requires_full,
                latest_version=latest, asset_name=asset_name,
                asset_url=str(selected_assets[0].get("browser_download_url") or ""),
                asset_size=sum(int(item.get("size") or 0) for item in selected_assets), release_url=str(release.get("html_url") or ""),
                release_notes=str(release.get("body") or ""),
                minimum_upgradable_version=MINIMUM_DIRECT_UPDATE_VERSION,
                requires_full_install=requires_full,
                message=(f"Full package required for versions older than {MINIMUM_DIRECT_UPDATE_VERSION}" if requires_full
                         else ("Update available" if available else "Already up to date")),
            )
        except Exception as exc:
            self._set(status="error", error=str(exc), message="Update check failed")
        return self.status()

    def start_download(self) -> dict[str, Any]:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return asdict(self._state)
            if not self._state.available or not self._state.asset_url:
                raise RuntimeError("No compatible application update is available")
            # Before the manifest is staged we do not yet know whether the
            # archive is app_only or runtime_replace.  Reserve conservatively
            # for the download, extraction, and rollback copy.
            free = shutil.disk_usage(get_app_root()).free
            required = max(self._state.asset_size * 3, 512 * 1024 * 1024)
            if free < required:
                raise RuntimeError(
                    f"Insufficient disk space for safe update: need at least {required / 1024**3:.1f} GiB free"
                )
            self._cancel.clear()
            self._state.status = "starting"
            self._state.error = ""
            self._worker = threading.Thread(target=self._download_and_stage, daemon=True, name="app-update-downloader")
            self._worker.start()
        return self.status()

    def cancel(self) -> dict[str, Any]:
        self._cancel.set()
        self._set(message="Cancelling application update download")
        return self.status()

    def _raise_if_cancelled(self) -> None:
        if self._cancel.is_set():
            raise InterruptedError("Application update download cancelled")

    def _download(self, url: str, destination: Path) -> None:
        existing = destination.stat().st_size if destination.is_file() else 0
        local = Path(os.path.expandvars(os.path.expanduser(url)))
        headers = {"Range": f"bytes={existing}-"} if existing and not local.is_file() else None
        try:
            response = self._open_url(url, headers=headers)
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and existing:
                return
            raise
        with response:
            resumed = existing > 0 and (local.is_file() or getattr(response, "status", None) == 206)
            if resumed and local.is_file():
                if existing <= local.stat().st_size:
                    response.seek(existing)
                else:
                    resumed = False
            downloaded = existing if resumed else 0
            length = int(getattr(response, "headers", {}).get("Content-Length", 0) or 0)
            total = downloaded + length if length else self._state.asset_size
            self._set(status="downloading", message="Resuming application update" if resumed else "Downloading application update")
            with destination.open("ab" if resumed else "wb") as output:
                while True:
                    self._raise_if_cancelled()
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    output.write(block)
                    downloaded += len(block)
                    self._set(bytes_downloaded=downloaded, bytes_total=total, progress=(downloaded / total * 0.75) if total else 0.25)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _safe_extract(archive: Path, destination: Path) -> None:
        root = destination.resolve()
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                target = (root / item.filename).resolve()
                if target != root and root not in target.parents:
                    raise RuntimeError(f"Unsafe path in update archive: {item.filename}")
            bundle.extractall(root)

    def _validate_staging(self, staging: Path) -> None:
        manifest_path = staging / "app-update-build.json"
        exe = staging / "Stream Translator.exe"
        if not manifest_path.is_file() or not exe.is_file():
            raise RuntimeError("Update package is missing its manifest or executable")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        schema = int(manifest.get("schema") or 0)
        if schema not in {1, 2} or manifest.get("profile") != self._state.profile:
            raise RuntimeError("Update package profile or schema does not match this installation")
        if str(manifest.get("version")) != self._state.latest_version:
            raise RuntimeError("Update package version does not match the selected Release")
        minimum = str(manifest.get("minimum_upgradable_version") or "")
        requires_full = bool(manifest.get("requires_full_install", False))
        update_mode = str(manifest.get("update_mode") or ("runtime_replace" if (staging / "_runtime").exists() else "app_only"))
        if schema == 1 and (staging / "_runtime").exists():
            raise RuntimeError("Legacy update package contains an unsafe partial _runtime; use the Full package")
        if update_mode not in UPDATE_MODES:
            raise RuntimeError(f"Unsupported update mode: {update_mode}")
        runtime = staging / "_runtime"
        if update_mode == "app_only" and runtime.exists():
            raise RuntimeError("app_only update must not contain _runtime")
        if update_mode == "runtime_replace":
            required = (runtime / "python.exe", runtime / "runtime-version.json")
            if not all(path.is_file() for path in required):
                raise RuntimeError("runtime_replace update must contain a complete _runtime")
            runtime_manifest = json.loads((runtime / "runtime-version.json").read_text(encoding="utf-8"))
            if str(runtime_manifest.get("profile") or "").lower() != self._state.profile:
                raise RuntimeError("Replacement runtime profile does not match this installation")
        self._set(minimum_upgradable_version=minimum, requires_full_install=requires_full, update_mode=update_mode)
        if requires_full or (minimum and self._version_tuple(self._state.current_version) < self._version_tuple(minimum)):
            raise RuntimeError(f"此版本需要下載同 Profile Full 包安裝（最低可直接升級版本：{minimum or '不適用'}）")
        unexpected = sorted(item.name for item in staging.iterdir() if item.name not in ALLOWED_UPDATE_NAMES)
        if unexpected:
            raise RuntimeError(f"Update package contains unexpected or protected data: {', '.join(unexpected)}")

    def _download_and_stage(self) -> None:
        try:
            update_root = get_app_root() / ".app-update"
            downloads = update_root / "downloads"
            downloads.mkdir(parents=True, exist_ok=True)
            assets = self._assets or [{
                "name": self._state.asset_name,
                "browser_download_url": self._state.asset_url,
                "size": self._state.asset_size,
                "digest": f"sha256:{self._expected_digest}",
            }]
            downloaded_parts: list[Path] = []
            total_size = sum(int(item.get("size") or 0) for item in assets)
            completed_size = 0
            for index, asset in enumerate(assets):
                part = downloads / f"{asset['name']}.part"
                self._set(asset_url=str(asset.get("browser_download_url") or ""), asset_size=total_size)
                self._download(str(asset.get("browser_download_url") or ""), part)
                actual_part = self._sha256(part)
                expected_part = str(asset.get("digest") or "").removeprefix("sha256:").lower()
                if not expected_part or actual_part != expected_part:
                    part.unlink(missing_ok=True)
                    raise RuntimeError(f"Update part SHA-256 mismatch: {asset.get('name')}")
                downloaded_parts.append(part)
                completed_size += part.stat().st_size
                self._set(bytes_downloaded=completed_size, bytes_total=total_size, progress=(completed_size / total_size * 0.75) if total_size else 0.25)
            archive = downloads / self._state.asset_name
            if len(downloaded_parts) == 1:
                shutil.copy2(downloaded_parts[0], archive)
            else:
                with archive.open("wb") as output:
                    for part in downloaded_parts:
                        with part.open("rb") as stream:
                            shutil.copyfileobj(stream, output, length=8 * 1024 * 1024)
            self._archive = archive
            self._raise_if_cancelled()
            self._set(status="verifying", message="Verifying application update", progress=0.78)
            actual = self._sha256(archive)
            if len(downloaded_parts) == 1 and self._expected_digest and actual != self._expected_digest:
                archive.unlink(missing_ok=True)
                raise RuntimeError(f"Application update SHA-256 mismatch: expected {self._expected_digest}, got {actual}")
            staging = update_root / f"staging-{self._state.latest_version}"
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            self._set(status="staging", message="Preparing application update", progress=0.84)
            self._safe_extract(archive, staging)
            self._validate_staging(staging)
            self._staging = staging
            self._set(status="ready", message="Application update is ready", progress=1.0, ready_to_apply=True)
        except InterruptedError:
            self._set(status="cancelled", message="Application update download cancelled")
        except Exception as exc:
            self._set(status="error", message="Application update preparation failed", error=str(exc))

    def create_apply_plan(self) -> dict[str, Any]:
        if not self._state.ready_to_apply or self._staging is None:
            raise RuntimeError("Application update is not ready to apply")
        app_root = get_app_root().resolve()
        staging = self._staging.resolve()
        if app_root not in staging.parents:
            raise RuntimeError("Invalid update staging path")
        updater = app_root / "StreamTranslatorUpdater.exe"
        if not updater.is_file():
            raise RuntimeError("StreamTranslatorUpdater.exe is missing")
        plan = {
            "schema": 2, "app_root": str(app_root), "staging": str(staging),
            "version": self._state.latest_version, "profile": self._state.profile,
            "update_mode": self._state.update_mode,
            "executable": "Stream Translator.exe", "parent_pid": os.getppid(),
        }
        plan_path = app_root / ".app-update" / "apply-plan.json"
        plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
        updater_copy = Path(tempfile.gettempdir()) / f"StreamTranslatorUpdater-{os.getpid()}.exe"
        shutil.copy2(updater, updater_copy)
        return {"plan_path": str(plan_path), "updater_path": str(updater_copy)}


app_update_manager = AppUpdateManager()
