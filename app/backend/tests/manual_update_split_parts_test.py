import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

from manual_update import prepare_package


class ManualUpdateTest(unittest.TestCase):
    def test_split_package_checks_missing_last_part_and_merged_digest(self):
        for failure in ("missing_last", "digest", "valid"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
                parent = Path(temp_dir)
                root = parent / "install"
                (root / "_runtime").mkdir(parents=True)
                (root / "Stream Translator.exe").write_bytes(b"old")
                (root / "config.yaml").write_text("{}", encoding="utf-8")
                (root / "_runtime/runtime-version.json").write_text(json.dumps({"profile": "cuda", "app_version": "1.4.0"}), encoding="utf-8")
                archive = parent / "update.zip"
                with zipfile.ZipFile(archive, "w") as bundle:
                    bundle.writestr("app-update-build.json", json.dumps({"schema": 2, "profile": "cuda", "version": "1.4.1", "update_mode": "app_only"}))
                    bundle.writestr("Stream Translator.exe", b"new")
                    bundle.writestr("StreamTranslatorUpdater.exe", b"updater")
                payload = archive.read_bytes()
                split = len(payload) // 2
                checksums = []
                for index, content in enumerate((payload[:split], payload[split:]), 1):
                    part = parent / f"update.zip.part{index:02d}"
                    if failure != "missing_last" or index == 1:
                        part.write_bytes(content)
                    checksums.append(f"{hashlib.sha256(content).hexdigest()}  {part.name}")
                digest = "0" * 64 if failure == "digest" else hashlib.sha256(payload).hexdigest()
                checksums.append(f"{digest}  update.zip")
                (parent / "SHA256SUMS-v1.4.1.txt").write_text("\n".join(checksums), encoding="utf-8")
                allowed = {"app-update-build.json", "Stream Translator.exe", "StreamTranslatorUpdater.exe"}
                if failure == "valid":
                    plan = prepare_package(parent / "update.zip.part01", root, allowed)
                    self.assertTrue(plan.is_file())
                else:
                    message = "分割包缺少檔案" if failure == "missing_last" else "合併後的 ZIP SHA-256 驗證失敗"
                    with self.assertRaisesRegex(RuntimeError, message):
                        prepare_package(parent / "update.zip.part01", root, allowed)
                self.assertEqual((root / "Stream Translator.exe").read_bytes(), b"old")
                self.assertEqual((root / "config.yaml").read_text(encoding="utf-8"), "{}")


if __name__ == "__main__":
    unittest.main()
