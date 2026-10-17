"""Verified, optional Janome wheel installation; never invokes pip."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
import uuid
from pathlib import Path, PurePosixPath

from backend.core.http_downloader import HttpDownloader
from backend.core.portable_paths import get_app_root

VERSION = "0.5.0"
URL = "https://files.pythonhosted.org/packages/73/7d/70f4069f4bbf0fca023e82a1fbbade6f5216365d4fe259fee1950723eca5/Janome-0.5.0-py2.py3-none-any.whl"
SIZE = 19654103
SHA256 = "d098670394a77881ce2f6b7d696c0ea5ff74c0c8cf74a8a882159ec82c0e6dc7"
BUSY = {"downloading", "installing"}


def _remove_scratch(path: Path) -> None:
    # Antivirus often holds a fresh download for a moment on Windows; a failed
    # cleanup must not fail the install, and the next install sweeps leftovers.
    for _ in range(5):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        time.sleep(0.5)


def install_directory() -> Path:
    return get_app_root() / "addons" / "janome-0.5.0"


def is_installed() -> bool:
    root = install_directory()
    try:
        manifest = json.loads((root / ".complete.json").read_text(encoding="utf-8"))
        return (manifest["sha256"] == SHA256 and manifest["size"] == SIZE
                and bool(manifest["files"])
                and all((root / name).is_file() and (root / name).stat().st_size == size
                        for name, size in manifest["files"].items())
                and (root / "janome" / "tokenizer.py").is_file())
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return False


def apply_reading_addon_environment(env: dict[str, str]) -> None:
    env.pop("STREAM_TRANSLATOR_READING_ADDON", None)
    if is_installed():
        env["STREAM_TRANSLATOR_READING_ADDON"] = str(install_directory())


class ReadingAddonInstaller:
    def __init__(self):
        self._lock = threading.RLock()
        self._state = "idle"
        self._progress = 0.0
        self._error = None

    def status(self):
        with self._lock:
            installed = is_installed()
            return {"installed": installed, "version": VERSION,
                    "size_bytes": SIZE if installed else None, "state": self._state,
                    "progress": self._progress, "error": self._error}

    def _set(self, state, progress, error=None):
        with self._lock:
            self._state, self._progress, self._error = state, progress, error

    def begin(self):
        with self._lock:
            if self._state in BUSY or is_installed():
                return self.status()
            self._set("downloading", 0.0)
            threading.Thread(target=self.install, daemon=True, name="reading-addon-install").start()
            return self.status()

    def install(self):
        try:
            target = install_directory()
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and not is_installed():
                os.rename(target, target.with_name(f".janome-removing-{uuid.uuid4().hex}"))
            for stale in target.parent.glob(".janome-*"):
                _remove_scratch(stale)
            temporary = Path(tempfile.mkdtemp(prefix=".janome-", dir=target.parent))
            try:
                wheel = temporary / "janome.whl"

                def progress(downloaded, total):
                    self._set("downloading", min(0.9, downloaded / SIZE * 0.9))

                # Same downloader/proxy environment as the model installer.
                HttpDownloader(progress=progress).download(URL, wheel)
                if wheel.stat().st_size != SIZE:
                    raise RuntimeError("Janome size mismatch")
                digest = hashlib.sha256()
                with wheel.open("rb") as source:
                    for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
                        digest.update(block)
                if digest.hexdigest() != SHA256:
                    raise RuntimeError("Janome SHA-256 mismatch")
                self._set("installing", 0.95)
                staged = temporary / "installed"
                staged.mkdir()
                files = {}
                with zipfile.ZipFile(wheel) as archive:
                    for member in archive.infolist():
                        path = PurePosixPath(member.filename)
                        if (path.is_absolute() or ".." in path.parts or "\\" in member.filename
                                or ":" in member.filename):
                            raise RuntimeError("Unsafe Janome wheel path")
                        if not path.parts or not (path.parts[0] == "janome" or
                                                   path.parts[0] == "Janome-0.5.0.dist-info"):
                            continue
                        if member.is_dir():
                            continue
                        destination = staged.joinpath(*path.parts)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, destination.open("wb") as output:
                            shutil.copyfileobj(source, output)
                        files[path.as_posix()] = member.file_size
                if not (staged / "janome/tokenizer.py").is_file() or not (staged / "Janome-0.5.0.dist-info/METADATA").is_file():
                    raise RuntimeError("Incomplete Janome wheel")
                (staged / ".complete.json").write_text(json.dumps(
                    {"sha256": SHA256, "size": SIZE, "files": files}), encoding="utf-8")
                if target.exists():
                    raise RuntimeError("Janome directory already exists; remove it before reinstalling")
                os.rename(staged, target)
            finally:
                _remove_scratch(temporary)
            self._set("idle", 1.0)
        except Exception as exc:
            self._set("error", 0.0, str(exc))

    def remove(self):
        with self._lock:
            if self._state in BUSY:
                raise RuntimeError("Reading add-on installation is running")
            target = install_directory()
            # Fixed application-owned destination, never a caller-supplied path.
            try:
                if target.exists():
                    scratch = target.with_name(f".janome-removing-{uuid.uuid4().hex}")
                    os.rename(target, scratch)
                    _remove_scratch(scratch)
            except OSError as exc:
                message = "Unable to remove reading add-on; try again"
                self._set("error", 0.0, message)
                raise RuntimeError(message) from exc
            self._set("idle", 0.0)
            return self.status()


reading_addon_installer = ReadingAddonInstaller()
