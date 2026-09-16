"""Bounded parallel HTTP downloads with a resumable contiguous partial file."""
import os
import re
import threading
import urllib.request
import urllib.error
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DOWNLOAD_CONNECTIONS = 4
DOWNLOAD_CHUNK_SIZE = 8 * 1024 * 1024
DOWNLOAD_READ_SIZE = 1024 * 1024

class _RangeUnsupported(Exception):
    pass

class HttpDownloader:
    def __init__(self, progress=None):
        self._cancel = threading.Event()
        self._progress = progress

    def _set(self, **changes):
        if self._progress and 'bytes_downloaded' in changes:
            self._progress(changes['bytes_downloaded'], changes.get('bytes_total', 0))

    def _raise_if_cancelled(self):
        if self._cancel.is_set():
            raise InterruptedError('Download cancelled')

    def download(self, url: str, destination: Path):
        self._download(url, destination)

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
        self._raise_if_cancelled()
        if urllib.parse.urlsplit(url).scheme in {"http", "https"}:
            try:
                if self._download_parallel(url, destination):
                    return
            except _RangeUnsupported:
                # Only a contiguous, completed prefix is ever persisted.
                self._raise_if_cancelled()
        self._download_single(url, destination)

    def _download_parallel(self, url: str, destination: Path) -> bool:
        self._set(status="downloading", message="Checking multi-connection download support")
        with self._open_url(url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity"}) as probe:
            match = re.fullmatch(r"bytes 0-0/(\d+)", probe.headers.get("Content-Range", ""))
            if probe.status != 206 or not match:
                return False
            total = int(match.group(1))
            validator = probe.headers.get("ETag", "")
            if validator.startswith('W/'):
                validator = ""
            validator = validator or probe.headers.get("Last-Modified", "")
        existing = destination.stat().st_size if destination.is_file() else 0
        if existing > total:
            destination.write_bytes(b"")
            existing = 0
        if total - existing < 2 * DOWNLOAD_CHUNK_SIZE:
            return False

        self._set(message=f"Downloading CPU ASR runtime ({DOWNLOAD_CONNECTIONS} connections)",
                  bytes_downloaded=existing, bytes_total=total, progress=existing / total * 0.75)
        stopped = threading.Event()
        progress_lock = threading.Lock()
        in_flight: dict[int, int] = {}
        batch_base = existing
        def report_in_flight(start: int, received: int) -> None:
            # Workers receive ranges concurrently, while the file is still
            # committed in order below. Report received network bytes so a
            # slow 8 MB batch does not appear frozen at 0 B for minutes.
            with progress_lock:
                in_flight[start] = received
                visible_downloaded = min(total, batch_base + sum(in_flight.values()))
            self._set(
                bytes_downloaded=visible_downloaded,
                bytes_total=total,
                progress=visible_downloaded / total * 0.75,
            )

        def fetch(start: int, end: int) -> bytes:
            headers = {"Range": f"bytes={start}-{end}", "Accept-Encoding": "identity"}
            if validator:
                headers['If-Range'] = validator
            for attempt in range(3):
                report_in_flight(start, 0)
                self._raise_if_cancelled()
                if stopped.is_set():
                    raise InterruptedError("Parallel download stopped")
                try:
                    with self._open_url(url, headers=headers) as response:
                        if (response.status != 206 or
                                response.headers.get('Content-Range') != f'bytes {start}-{end}/{total}'):
                            raise _RangeUnsupported()
                        data = bytearray()
                        while len(data) < end - start + 1:
                            self._raise_if_cancelled()
                            if stopped.is_set():
                                raise InterruptedError("Parallel download stopped")
                            block = response.read(min(DOWNLOAD_READ_SIZE, end - start + 1 - len(data)))
                            if not block:
                                raise OSError("Incomplete CPU ASR download range")
                            data.extend(block)
                            report_in_flight(start, len(data))
                        return bytes(data)
                except InterruptedError:
                    raise
                except (OSError, urllib.error.URLError):
                    if attempt == 2:
                        raise
                    if self._cancel.wait(0.25 * (attempt + 1)):
                        self._raise_if_cancelled()
            raise AssertionError("unreachable")

        # Bounded batches avoid buffering the whole archive. Appending in order
        # keeps the existing .part format resumable after cancellation/crashes.
        with ThreadPoolExecutor(max_workers=DOWNLOAD_CONNECTIONS) as pool:
            try:
                with destination.open('ab') as output:
                    position = existing
                    while position < total:
                        self._raise_if_cancelled()
                        batch_base = position
                        with progress_lock:
                            in_flight.clear()
                        starts = range(position, min(total, position + DOWNLOAD_CONNECTIONS * DOWNLOAD_CHUNK_SIZE),
                                       DOWNLOAD_CHUNK_SIZE)
                        futures = [pool.submit(fetch, start, min(total - 1, start + DOWNLOAD_CHUNK_SIZE - 1))
                                   for start in starts]
                        for future in futures:
                            data = future.result()
                            self._raise_if_cancelled()
                            output.write(data)
                            output.flush()
                            position += len(data)
                            self._set(bytes_downloaded=position, bytes_total=total,
                                      progress=position / total * 0.75)
            finally:
                stopped.set()
        return True

    def _download_single(self, url: str, destination: Path) -> None:
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
