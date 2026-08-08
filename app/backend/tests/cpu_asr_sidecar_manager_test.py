import os
import sys
import tempfile
import time
import types
import unittest
import zipfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

config_stub = types.ModuleType("backend.config")
config_stub.settings = types.SimpleNamespace(APP_VERSION="1.3.10")
paths_stub = types.ModuleType("backend.core.portable_paths")
paths_stub.get_app_root = lambda: APP_DIR
paths_stub.get_cpu_asr_runtime_path = lambda: APP_DIR / "_runtime_cpu_asr"
sys.modules.setdefault("backend.config", config_stub)
sys.modules.setdefault("backend.core.portable_paths", paths_stub)

from backend.core import cpu_asr_sidecar_manager as sidecar_module


class CpuAsrSidecarManagerTest(unittest.TestCase):
    def test_rejects_zip_slip_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escaped.txt", "unsafe")
            with self.assertRaisesRegex(RuntimeError, "Unsafe path"):
                sidecar_module.CpuAsrSidecarManager._safe_extract(archive, root / "extract")

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
