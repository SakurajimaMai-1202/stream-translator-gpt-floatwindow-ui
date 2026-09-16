import os
import sys
import tempfile
import time
import types
import unittest
import zipfile
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

config_stub = types.ModuleType("backend.config")
config_stub.settings = types.SimpleNamespace(APP_VERSION="1.3.11")
paths_stub = types.ModuleType("backend.core.portable_paths")
paths_stub.get_app_root = lambda: APP_DIR
paths_stub.get_cpu_asr_runtime_path = lambda: APP_DIR / "_runtime_cpu_asr"
sys.modules.setdefault("backend.config", config_stub)
sys.modules.setdefault("backend.core.portable_paths", paths_stub)

from backend.core import cpu_asr_sidecar_manager as sidecar_module
from backend.core import http_downloader as download_module


@contextmanager
def range_server(mode="ranges"):
    payload = bytes(range(256)) * 512
    stats = {"active": 0, "peak": 0, "ranges": [], "truncated": False}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            requested = self.headers.get('Range')
            with lock:
                stats['ranges'].append(requested)
            if requested and mode != 'ignore':
                first, last = requested.removeprefix('bytes=').split('-')
                start, end = int(first), int(last) if last else len(payload) - 1
                if mode == 'ignore_chunks' and last and requested != 'bytes=0-0':
                    self.send_response(200)
                    body = payload
                else:
                    self.send_response(206)
                    self.send_header('Content-Range', f'bytes {start}-{end}/{len(payload)}')
                    body = payload[start:end + 1]
            else:
                self.send_response(200)
                body = payload
            self.send_header('Content-Length', str(len(body)))
            self.send_header('ETag', '"fixture-v1"')
            self.end_headers()
            with lock:
                stats['active'] += 1
                stats['peak'] = max(stats['peak'], stats['active'])
                truncate = mode == 'truncate' and len(body) > 1 and not stats['truncated']
                if truncate:
                    stats['truncated'] = True
            try:
                time.sleep(0.02)
                self.wfile.write(body[:len(body) // 2] if truncate else body)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with lock:
                    stats['active'] -= 1

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_port}/asset.zip', payload, stats
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class CpuAsrSidecarManagerTest(unittest.TestCase):
    def test_parallel_http_download_and_resume(self):
        with range_server() as (url, payload, stats), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'asset.part'
            path.write_bytes(payload[:123])
            manager = sidecar_module.CpuAsrSidecarManager()
            with mock.patch.object(download_module, 'DOWNLOAD_CHUNK_SIZE', 8192):
                manager._download(url, path)
            self.assertEqual(path.read_bytes(), payload)
            self.assertGreater(stats['peak'], 1)
            self.assertIn('bytes=123-8314', stats['ranges'])
            self.assertEqual(manager._state.bytes_downloaded, len(payload))

    def test_parallel_download_reports_bytes_inside_a_range(self):
        with range_server() as (url, payload, _), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'asset.part'
            progress = []
            downloader = download_module.HttpDownloader(
                progress=lambda downloaded, total: progress.append((downloaded, total))
            )
            with mock.patch.object(download_module, 'DOWNLOAD_CHUNK_SIZE', 8192), \
                 mock.patch.object(download_module, 'DOWNLOAD_READ_SIZE', 1024):
                downloader.download(url, path)

            self.assertEqual(path.read_bytes(), payload)
            self.assertTrue(any(0 < downloaded < 8192 for downloaded, _ in progress))
            self.assertEqual(progress[-1], (len(payload), len(payload)))

    def test_http_range_fallback(self):
        for mode in ('ignore', 'ignore_chunks'):
            with self.subTest(mode=mode), range_server(mode) as (url, payload, _), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'asset.part'
                manager = sidecar_module.CpuAsrSidecarManager()
                with mock.patch.object(download_module, 'DOWNLOAD_CHUNK_SIZE', 8192):
                    manager._download(url, path)
                self.assertEqual(path.read_bytes(), payload)

    def test_parallel_retries_truncated_range(self):
        with range_server('truncate') as (url, payload, stats), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'asset.part'
            manager = sidecar_module.CpuAsrSidecarManager()
            with mock.patch.object(download_module, 'DOWNLOAD_CHUNK_SIZE', 8192):
                manager._download(url, path)
            self.assertTrue(stats['truncated'])
            self.assertEqual(path.read_bytes(), payload)

    def test_cancel_parallel_download_preserves_contiguous_prefix(self):
        with range_server() as (url, payload, _), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'asset.part'
            manager = sidecar_module.CpuAsrSidecarManager()
            update = manager._set

            def cancel_after_chunk(**changes):
                update(**changes)
                if changes.get('bytes_downloaded', 0) >= 8192:
                    manager._cancel.set()

            with mock.patch.object(download_module, 'DOWNLOAD_CHUNK_SIZE', 8192):
                with mock.patch.object(manager, '_set', side_effect=cancel_after_chunk):
                    with self.assertRaises(InterruptedError):
                        manager._download(url, path)
                partial = path.read_bytes()
                self.assertEqual(partial, payload[:len(partial)])
                self.assertLess(len(partial), len(payload))
                manager._cancel.clear()
                manager._download(url, path)
            self.assertEqual(path.read_bytes(), payload)
    def test_rejects_zip_slip_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escaped.txt", "unsafe")
            with self.assertRaisesRegex(RuntimeError, "Unsafe path"):
                sidecar_module.CpuAsrSidecarManager._safe_extract(archive, root / "extract")

    def test_runtime_health_is_cached_until_runtime_changes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime = Path(temp_dir)
            (runtime / "python.exe").write_bytes(b"python")
            manifest = runtime / "runtime-version.json"
            manifest.write_text("{}", encoding="utf-8")
            manager = sidecar_module.CpuAsrSidecarManager()
            with mock.patch.object(manager, "_validate_runtime") as validate:
                self.assertEqual(manager._runtime_health(runtime), (True, ""))
                self.assertEqual(manager._runtime_health(runtime), (True, ""))
                self.assertEqual(validate.call_count, 1)
                manifest.write_text('{"profile":"cpu"}', encoding="utf-8")
                self.assertEqual(manager._runtime_health(runtime), (True, ""))
                self.assertEqual(validate.call_count, 2)

    def test_cancel_marks_active_download_for_cancellation(self):
        manager = sidecar_module.CpuAsrSidecarManager()
        manager._worker = mock.Mock()
        manager._worker.is_alive.return_value = True
        manager._state.status = "downloading"
        manager.cancel()
        self.assertTrue(manager._cancel.is_set())
        self.assertEqual(manager._state.message, "Cancelling CPU ASR runtime download")

    def test_installing_phase_is_not_cancelled(self):
        manager = sidecar_module.CpuAsrSidecarManager()
        manager._worker = mock.Mock()
        manager._worker.is_alive.return_value = True
        manager._state.status = "installing"
        manager.cancel()
        self.assertFalse(manager._cancel.is_set())

    def test_download_stops_when_cancelled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.zip"
            source.write_bytes(b"sidecar")
            manager = sidecar_module.CpuAsrSidecarManager()
            manager._cancel.set()
            with self.assertRaisesRegex(InterruptedError, "cancelled"):
                manager._download(str(source), root / "download.zip")

    def test_download_resumes_existing_partial_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.zip"
            destination = root / "download.zip.part"
            source.write_bytes(b"sidecar-runtime")
            destination.write_bytes(b"side")
            manager = sidecar_module.CpuAsrSidecarManager()
            manager._download(str(source), destination)
            self.assertEqual(destination.read_bytes(), source.read_bytes())
            self.assertEqual(manager._state.message, "Resuming CPU ASR runtime download")

    @unittest.skipUnless(os.environ.get("CPU_ASR_SIDECAR_TEST_ASSET"), "real sidecar asset not provided")
    def test_real_sidecar_install(self):
        asset = Path(os.environ["CPU_ASR_SIDECAR_TEST_ASSET"]).resolve()
        with tempfile.TemporaryDirectory(dir=APP_DIR, prefix="sidecar-install-") as temp_dir:
            target = Path(temp_dir) / "_runtime_cpu_asr"
            sidecar_module.get_cpu_asr_runtime_path = lambda: target
            os.environ["STREAM_TRANSLATOR_CPU_ASR_SIDECAR_URL"] = str(asset)
            manager = sidecar_module.CpuAsrSidecarManager()
            manager.start()
            deadline = time.monotonic() + 300
            while manager.status()["status"] in {"starting", "downloading", "verifying", "installing"}:
                self.assertLess(time.monotonic(), deadline, "sidecar install timed out")
                time.sleep(0.25)
            status = manager.status()
            self.assertEqual(status["status"], "completed", status)
            self.assertTrue(status["installed"])
            self.assertTrue(status["restart_required"])


if __name__ == "__main__":
    unittest.main()
