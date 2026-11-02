"""Verified optional yt-dlp wheels, selected without PYTHONPATH or pip."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from backend.core.external_process import run_external
from backend.core.http_downloader import HttpDownloader
from backend.core.portable_paths import get_app_root
from backend.core.reading_addon_installer import _remove_scratch

logger = logging.getLogger(__name__)

BOOTSTRAP = "import sys;sys.path.insert(0,sys.argv.pop(1));sys.argv[0]='yt-dlp';import yt_dlp;yt_dlp.main()"
BUSY = {"checking", "downloading", "installing"}
BUNDLED_RETRY_SECONDS = 60
_bundled = None
_bundled_retry_at = 0.0
_version_lock = threading.RLock()


def parse_version(text):
    if not isinstance(text, str):
        return None
    match = re.fullmatch(r"(\d+\.\d+\.\d+(?:\.\d+)?)(\.dev0)?", text)
    if not match:
        return None
    release = tuple(int(part) for part in match[1].split('.'))
    return release + (0,) * (4 - len(release)) + (0 if match[2] else 1,)


def _same_release(left, right):
    # A nightly wheel is 2026.10.29.232701.dev0 but `yt-dlp --version` prints it without .dev0.
    first, second = parse_version(left), parse_version(right)
    return first is not None and second is not None and first[:-1] == second[:-1]


def _runtime_python():
    from backend.core.cookie_manager import _resolve_runtime_python
    python = _resolve_runtime_python()
    if getattr(sys, 'frozen', False) and Path(python).resolve() == Path(sys.executable).resolve():
        raise RuntimeError('找不到 Python 執行環境。')
    return str(python)


def _run(command, timeout):
    # Same launcher as the engine, so the smoke test sees the environment the engine will.
    return run_external(command, capture_output=True, text=True, encoding='utf-8',
                        errors='replace', timeout=timeout,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))


def bundled_version():
    global _bundled, _bundled_retry_at
    with _version_lock:
        if _bundled is not None or time.monotonic() < _bundled_retry_at:
            return _bundled
        try:
            result = _run([_runtime_python(), '-I', '-c',
                           "import importlib.metadata;print(importlib.metadata.version('yt-dlp'))"], 20)
            if not result.returncode and result.stdout.strip():
                _bundled = result.stdout.strip()
                return _bundled
        except Exception:
            logger.warning('Could not read the bundled yt-dlp version', exc_info=True)
        # A slow first run (antivirus) must not pin "unknown" until the next restart.
        _bundled_retry_at = time.monotonic() + BUNDLED_RETRY_SECONDS
        return None


def _root():
    return get_app_root() / 'addons'


def _safe_path(name):
    path = PurePosixPath(name)
    if not path.parts or path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
        raise ValueError('套件含有不安全的路徑。')
    return path


def _pointer_directory():
    pointer = json.loads((_root() / 'yt-dlp-active.json').read_text(encoding='utf-8'))
    version = pointer['version']
    if parse_version(version) is None or pointer['directory'] != f'yt-dlp-{version}':
        raise ValueError('無效的套件指標。')
    directory = _root() / pointer['directory']
    if directory.resolve().parent != _root().resolve():
        raise ValueError('無效的套件路徑。')
    return directory, version


def active_addon():
    try:
        directory, version = _pointer_directory()
        manifest = json.loads((directory / '.complete.json').read_text(encoding='utf-8'))
        if manifest['version'] != version or not manifest['files']:
            return None
        for name, size in manifest['files'].items():
            path = directory.joinpath(*_safe_path(name).parts)
            if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file() or path.stat().st_size != size:
                return None
        if not (directory / 'yt_dlp/__main__.py').is_file():
            return None
        bundled = parse_version(bundled_version())
        return directory if bundled is None or parse_version(version) > bundled else None
    except Exception:
        return None


def ytdlp_command(python):
    addon = active_addon()
    # -I drops PYTHONUTF8; without -X utf8 yt-dlp's stderr uses the console code page.
    prefix = [str(python), '-I', '-X', 'utf8']
    return prefix + (['-c', BOOTSTRAP, str(addon)] if addon else ['-m', 'yt_dlp'])


def apply_ytdlp_addon_environment(env):
    env.pop('STREAM_TRANSLATOR_YTDLP_ADDON', None)
    addon = active_addon()
    if addon:
        env['STREAM_TRANSLATOR_YTDLP_ADDON'] = str(addon)


def _fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'FloatWindow-yt-dlp-updater'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _wheel(metadata):
    wheels = [item for item in metadata['urls'] if not item.get('yanked')
              and item['filename'].endswith('-py3-none-any.whl')]
    if len(wheels) != 1:
        raise ValueError('找不到唯一的相容套件。')
    wheel = wheels[0]
    digest = wheel.get('digests', {}).get('sha256', '')
    if not re.fullmatch(r'[0-9a-fA-F]{64}', digest):
        raise ValueError('套件缺少 SHA-256。')
    if type(wheel.get('size')) is not int or wheel['size'] <= 0:
        raise ValueError('套件大小無效。')
    url = urlparse(wheel['url'])
    if url.scheme != 'https' or url.netloc != 'files.pythonhosted.org':
        raise ValueError('套件下載網址不受信任。')
    return wheel


def _ejs_pin(requirements):
    pins = []
    for requirement in requirements or []:
        if not re.match(r'^yt[-_]dlp[-_]ejs\b', requirement, re.I):
            continue
        if not re.search(r'''extra\s*==\s*['"]default['"]''', requirement):
            continue
        match = re.fullmatch(r'''yt[-_]dlp[-_]ejs\s*(?:\(\s*)?==\s*(\d+(?:\.\d+)*)(?:\s*\))?\s*;\s*extra\s*==\s*['"]default['"]\s*''', requirement, re.I)
        if not match:
            raise ValueError('yt-dlp-ejs 必須指定確切版本。')
        pins.append(match[1])
    if len(pins) != 1:
        raise ValueError('缺少 yt-dlp-ejs 確切版本。')
    return pins[0]


class YtDlpAddonManager:
    def __init__(self):
        self._lock = threading.RLock()
        self._state, self._progress, self._error = 'idle', 0.0, None
        self._latest = None
        self._install_running = False

    def _set(self, state, progress=0.0, error=None):
        with self._lock:
            self._state, self._progress, self._error = state, progress, error

    def status(self):
        # The first read may run a subprocess; do it before taking the state lock.
        bundled = bundled_version()
        with self._lock:
            addon = active_addon()
            active = addon.name.removeprefix('yt-dlp-') if addon else bundled
            latest, effective = parse_version(self._latest), parse_version(active)
            return dict(bundled_version=bundled, active_version=active, latest_version=self._latest,
                        update_available=latest is not None and (effective is None or latest > effective),
                        state=self._state, progress=self._progress, error=self._error)

    def check(self):
        with self._lock:
            if self._state in BUSY:
                raise RuntimeError('yt-dlp 正在更新，請稍候。')
            self._set('checking')
        try:
            metadata = _fetch('https://pypi.org/pypi/yt-dlp/json')
            versions = [v for v, files in metadata['releases'].items()
                        if parse_version(v) is not None and any(not f.get('yanked') for f in files)]
            with self._lock:
                self._latest = max(versions, key=parse_version)
                self._set('idle')
        except Exception:
            logger.warning('yt-dlp update check failed', exc_info=True)
            self._set('error', error='無法檢查 yt-dlp 更新，請稍後再試。')
        return self.status()

    def begin(self):
        with self._lock:
            if self._state in BUSY:
                raise RuntimeError('yt-dlp 正在更新，請稍候。')
            if not self.status()['update_available']:
                raise RuntimeError('沒有可用的較新 yt-dlp 版本。')
            self._set('downloading')
            threading.Thread(target=self.install, daemon=True, name='ytdlp-addon-install').start()
            return self.status()

    def _sweep(self, keep=None):
        for path in _root().iterdir():
            if path.is_dir() and (path.name.startswith('.yt-dlp-') or
                                 (path.name.startswith('yt-dlp-') and path != keep)):
                _remove_scratch(path)

    def install(self):
        with self._lock:
            if self._install_running or self._state in {'checking', 'installing'}:
                raise RuntimeError('yt-dlp 正在更新，請稍候。')
            self._install_running = True
        temporary = None
        error = None
        try:
            with self._lock:
                version = self._latest
                if not self.status()['update_available']:
                    raise ValueError('沒有可用的新版本。')
                self._set('downloading')
            root = _root()
            root.mkdir(parents=True, exist_ok=True)
            # A damaged add-on is not kept: its folder would block reinstalling that version.
            self._sweep(active_addon())
            metadata = _fetch(f'https://pypi.org/pypi/yt-dlp/{version}/json')
            ejs = _ejs_pin(metadata['info'].get('requires_dist'))
            wheels = [_wheel(metadata), _wheel(_fetch(f'https://pypi.org/pypi/yt-dlp-ejs/{ejs}/json'))]
            temporary = Path(tempfile.mkdtemp(prefix='.yt-dlp-', dir=root))
            staged = temporary / 'installed'
            staged.mkdir()
            files, hashes = {}, {}
            total = sum(w['size'] for w in wheels)
            downloaded = 0
            for index, wheel in enumerate(wheels):
                destination = temporary / f'{index}.whl'
                def progress(count, _total):
                    self._set('downloading', min(0.9, (downloaded + count) / total * 0.9))
                HttpDownloader(progress=progress).download(wheel['url'], destination)
                hasher = hashlib.sha256()
                with destination.open('rb') as source:
                    for block in iter(lambda: source.read(4 * 1024 * 1024), b''):
                        hasher.update(block)
                digest = hasher.hexdigest()
                if destination.stat().st_size != wheel['size'] or digest != wheel['digests']['sha256'].lower():
                    raise ValueError('套件大小或 SHA-256 驗證失敗。')
                downloaded += wheel['size']
                hashes[wheel['filename']] = digest
                with zipfile.ZipFile(destination) as archive:
                    for member in archive.infolist():
                        path = _safe_path(member.filename)
                        top = path.parts[0]
                        if top not in {'yt_dlp', 'yt_dlp_ejs'} and not re.fullmatch(r'yt_dlp(?:_ejs)?-[^/]+\.dist-info', top):
                            continue
                        if member.is_dir():
                            continue
                        output = staged.joinpath(*path.parts)
                        output.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, output.open('wb') as target:
                            shutil.copyfileobj(source, target)
                        files[path.as_posix()] = member.file_size
            self._set('installing', 0.95)
            if not all((staged / name).is_file() for name in ('yt_dlp/__main__.py', 'yt_dlp_ejs/__init__.py')):
                raise ValueError('套件內容不完整。')
            (staged / '.complete.json').write_text(json.dumps(dict(version=version, ejs_version=ejs,
                wheels=hashes, files=files)), encoding='utf-8')
            python = _runtime_python()
            result = _run([python, '-I', '-c', BOOTSTRAP, str(staged), '--version'], 60)
            if result.returncode or not _same_release(result.stdout.strip(), version):
                raise ValueError('版本測試失敗。')
            smoke = "import sys;sys.path.insert(0,sys.argv.pop(1));from pathlib import Path;import yt_dlp;from yt_dlp import YoutubeDL;import yt_dlp_ejs;assert Path(yt_dlp.__file__).resolve().is_relative_to(Path(sys.path[0]).resolve())"
            if _run([python, '-I', '-c', smoke, str(staged)], 60).returncode:
                raise ValueError('套件載入測試失敗。')
            target = root / f'yt-dlp-{version}'
            os.rename(staged, target)
            pointer = temporary / 'pointer.json'
            pointer.write_text(json.dumps(dict(version=version, directory=target.name)), encoding='utf-8')
            os.replace(pointer, root / 'yt-dlp-active.json')
        except Exception:
            logger.warning('yt-dlp update failed', exc_info=True)
            error = 'yt-dlp 更新失敗，已保留目前版本。請檢查網路或稍後再試。'
        finally:
            if temporary is not None:
                _remove_scratch(temporary)
            with self._lock:
                self._install_running = False
                self._set('error' if error else 'idle', 0.0 if error else 1.0, error)

    def restore_bundled(self):
        with self._lock:
            if self._state in BUSY:
                raise RuntimeError('yt-dlp 正在更新，請稍候。')
            try:
                (_root() / 'yt-dlp-active.json').unlink(missing_ok=True)
                if _root().exists():
                    self._sweep()
                self._set('idle')
            except OSError as exc:
                self._set('error', error='無法還原內建版本，請稍後再試。')
                raise RuntimeError(self._error) from exc
            return self.status()


ytdlp_addon_manager = YtDlpAddonManager()
