import hashlib
import json
import sys
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock


APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))

from backend.core import app_update_manager as update_module
from updater import Worker


class AppUpdateManagerTest(unittest.TestCase):
    def test_current_app_version_ignores_stale_runtime_manifest(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            runtime = root / "_runtime"
            runtime.mkdir()
            (runtime / "runtime-version.json").write_text(
                json.dumps({"app_version": "1.3.2", "profile": "cuda"}),
                encoding="utf-8",
            )
            with mock.patch.object(update_module, "get_app_root", return_value=root), mock.patch.object(
                update_module, "get_packaged_runtime_profile", return_value="cuda"
            ), mock.patch.object(update_module.settings, "APP_VERSION", "1.4.0"):
                manager = update_module.AppUpdateManager()

            self.assertEqual(manager.status()["current_version"], "1.4.0")

    def test_stale_runtime_manifest_does_not_offer_current_release(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            runtime = root / "_runtime"
            runtime.mkdir()
            (runtime / "runtime-version.json").write_text(
                json.dumps({"app_version": "1.3.2", "profile": "cuda"}),
                encoding="utf-8",
            )
            release = root / "release.json"
            release.write_text(
                json.dumps({
                    "tag_name": "v1.4.0",
                    "html_url": "https://example.test/v1.4.0",
                    "body": "Current release",
                    "assets": [{
                        "name": "StreamTranslator-CUDA-App-Update.zip",
                        "browser_download_url": "https://example.test/update.zip",
                        "size": 123,
                        "digest": "sha256:" + ("0" * 64),
                    }],
                }),
                encoding="utf-8",
            )
            with mock.patch.object(update_module, "get_app_root", return_value=root), mock.patch.object(
                update_module, "get_packaged_runtime_profile", return_value="cuda"
            ), mock.patch.object(update_module.settings, "APP_VERSION", "1.4.0"):
                manager = update_module.AppUpdateManager()
                checked = manager.check(release_api=str(release))

            self.assertEqual(checked["current_version"], "1.4.0")
            self.assertEqual(checked["status"], "up_to_date")
            self.assertFalse(checked["available"])

    def test_user_settings_snapshot_contains_config_rules_and_cookies(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root=Path(temp_dir)
            (root/"cookies").mkdir()
            (root/"cookies"/"youtube.cookies.txt").write_text("secret-cookie",encoding="utf-8")
            (root/"config.yaml").write_text(
                "input:\n  cookies_by_site:\n    youtube: cookies/youtube.cookies.txt\n"
                "terminology:\n  glossary_list:\n    - original: test\n      translated: 測試\n"
                "transcription:\n  asr_correction_rules:\n    - canonical: VTuber\n      aliases: [V tuber]\n",
                encoding="utf-8",
            )
            snapshot=Worker.backup_user_settings(root,"1.4.0")
            self.assertEqual((snapshot/"config.yaml").read_text(encoding="utf-8"),(root/"config.yaml").read_text(encoding="utf-8"))
            self.assertEqual(json.loads((snapshot/"custom-glossary.json").read_text(encoding="utf-8"))[0]["translated"],"測試")
            self.assertEqual(json.loads((snapshot/"asr-correction-rules.json").read_text(encoding="utf-8"))[0]["canonical"],"VTuber")
            self.assertEqual((snapshot/"cookies"/"youtube.cookies.txt").read_text(encoding="utf-8"),"secret-cookie")
            self.assertTrue((snapshot/"backup-manifest.json").is_file())

    def test_user_settings_snapshots_keep_only_latest_five(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root=Path(temp_dir); parent=root/".app-update"/"user-backups"; parent.mkdir(parents=True)
            for index in range(6):
                backup=parent/f"before-1.3.{index}-{index:02d}"
                backup.mkdir(); (backup/"config.yaml").write_text(str(index),encoding="utf-8")
                timestamp=1_700_000_000+index
                import os
                os.utime(backup,(timestamp,timestamp))
            Worker.prune_user_backups(parent,keep=5)
            remaining=sorted(path.name for path in parent.iterdir())
            self.assertEqual(len(remaining),5)
            self.assertNotIn("before-1.3.0-00",remaining)
    def _fixture(self, root: Path, *, protected: bool = False, mode: str = "app_only", complete_runtime: bool = True):
        archive = root / "StreamTranslator-CUDA-App-Update.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("app-update-build.json", json.dumps({"schema": 2, "profile": "cuda", "version": "1.4.1", "update_mode": mode, "minimum_upgradable_version": "1.3.11", "requires_full_install": False}))
            bundle.writestr("Stream Translator.exe", b"fake executable")
            bundle.writestr("StreamTranslatorUpdater.exe", b"fake updater")
            bundle.writestr("_internal/version.txt", "1.4.1")
            if mode == "runtime_replace":
                bundle.writestr("_runtime/runtime-version.json", json.dumps({"profile": "cuda", "app_version": "1.4.1"}))
                if complete_runtime:
                    bundle.writestr("_runtime/python.exe", b"fake runtime python")
            if protected:
                bundle.writestr("config.yaml", "must not replace")
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        release = root / "release.json"
        release.write_text(json.dumps({
            "tag_name": "v1.4.1", "html_url": "https://example.test/v1.4.1", "body": "Test release",
            "assets": [{
                "name": archive.name, "browser_download_url": str(archive),
                "size": archive.stat().st_size, "digest": f"sha256:{digest}",
            }],
        }), encoding="utf-8")
        return archive, release

    def test_check_download_verify_and_stage_matching_profile(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            _, release = self._fixture(root)
            (root / "StreamTranslatorUpdater.exe").write_bytes(b"fake updater")
            with mock.patch.object(update_module, "get_app_root", return_value=root), mock.patch.object(
                update_module, "get_packaged_runtime_profile", return_value="cuda"
            ), mock.patch.object(update_module.settings, "APP_VERSION", "1.4.0"):
                manager = update_module.AppUpdateManager()
                checked = manager.check(release_api=str(release))
                self.assertTrue(checked["available"])
                manager.start_download()
                deadline = time.monotonic() + 30
                while manager.status()["status"] in {"starting", "downloading", "verifying", "staging"}:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                status = manager.status()
                self.assertEqual(status["status"], "ready", status)
                self.assertTrue(status["ready_to_apply"])
                plan = manager.create_apply_plan()
                self.assertTrue(Path(plan["plan_path"]).is_file())
                self.assertTrue(Path(plan["updater_path"]).is_file())

    def test_downloads_verifies_and_reassembles_multipart_update(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            archive, release_path = self._fixture(root, mode="runtime_replace")
            payload = archive.read_bytes()
            archive.unlink()
            split = len(payload) // 2
            parts = []
            for index, content in enumerate((payload[:split], payload[split:]), start=1):
                part = root / f"StreamTranslator-CUDA-App-Update.zip.part{index:02d}"
                part.write_bytes(content)
                parts.append({
                    "name": part.name, "browser_download_url": str(part), "size": part.stat().st_size,
                    "digest": f"sha256:{hashlib.sha256(content).hexdigest()}",
                })
            release = json.loads(release_path.read_text(encoding="utf-8"))
            release["assets"] = parts
            release_path.write_text(json.dumps(release), encoding="utf-8")
            with mock.patch.object(update_module, "get_app_root", return_value=root), mock.patch.object(
                update_module, "get_packaged_runtime_profile", return_value="cuda"
            ), mock.patch.object(update_module.settings, "APP_VERSION", "1.4.0"):
                manager = update_module.AppUpdateManager()
                manager.check(release_api=str(release_path))
                manager.start_download()
                deadline = time.monotonic() + 30
                while manager.status()["status"] in {"starting", "downloading", "verifying", "staging"}:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                self.assertEqual(manager.status()["status"], "ready", manager.status())
                self.assertEqual(manager.status()["update_mode"], "runtime_replace")

    def test_rejects_update_that_contains_protected_user_data(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            _, release = self._fixture(root, protected=True)
            with mock.patch.object(update_module, "get_app_root", return_value=root), mock.patch.object(
                update_module, "get_packaged_runtime_profile", return_value="cuda"
            ), mock.patch.object(update_module.settings, "APP_VERSION", "1.4.0"):
                manager = update_module.AppUpdateManager()
                manager.check(release_api=str(release))
                manager.start_download()
                deadline = time.monotonic() + 30
                while manager.status()["status"] in {"starting", "downloading", "verifying", "staging"}:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                self.assertEqual(manager.status()["status"], "error")
                self.assertIn("protected data", manager.status()["error"])

    def test_runtime_replace_requires_complete_matching_runtime(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            _, release = self._fixture(root, mode="runtime_replace", complete_runtime=False)
            with mock.patch.object(update_module, "get_app_root", return_value=root), mock.patch.object(
                update_module, "get_packaged_runtime_profile", return_value="cuda"
            ), mock.patch.object(update_module.settings, "APP_VERSION", "1.4.0"):
                manager = update_module.AppUpdateManager()
                manager.check(release_api=str(release))
                manager.start_download()
                deadline = time.monotonic() + 30
                while manager.status()["status"] in {"starting", "downloading", "verifying", "staging"}:
                    self.assertLess(time.monotonic(), deadline)
                    time.sleep(0.05)
                self.assertEqual(manager.status()["status"], "error")
                self.assertIn("complete _runtime", manager.status()["error"])

    def test_app_only_plan_preserves_existing_runtime(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            app_root = root / "install"
            staging = app_root / ".app-update" / "staging-1.4.1"
            staging.mkdir(parents=True)
            runtime = app_root / "_runtime"
            runtime.mkdir()
            (runtime / "python.exe").write_bytes(b"existing runtime")
            (staging / "Stream Translator.exe").write_bytes(b"new executable")
            (staging / "app-update-build.json").write_text(json.dumps({
                "schema": 2, "profile": "cuda", "version": "1.4.1", "update_mode": "app_only",
            }), encoding="utf-8")
            plan_path = app_root / ".app-update" / "apply-plan.json"
            plan_path.write_text(json.dumps({
                "schema": 2, "app_root": str(app_root), "staging": str(staging),
                "version": "1.4.1", "profile": "cuda", "update_mode": "app_only",
            }), encoding="utf-8")

            _plan, _manifest, _root, _staging, items, mode = Worker.validate_plan(plan_path)
            self.assertEqual(mode, "app_only")
            self.assertNotIn("_runtime", [item.name for item in items])
            self.assertEqual((runtime / "python.exe").read_bytes(), b"existing runtime")

    def test_rejects_zip_slip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive = root / "unsafe.zip"
            with zipfile.ZipFile(archive, "w") as bundle:
                bundle.writestr("../escaped.txt", "unsafe")
            with self.assertRaisesRegex(RuntimeError, "Unsafe path"):
                update_module.AppUpdateManager._safe_extract(archive, root / "extract")

    def test_external_updater_rolls_back_when_new_executable_cannot_start(self):
        with tempfile.TemporaryDirectory(dir=APP_DIR) as temp_dir:
            root = Path(temp_dir)
            app_root = root / "install"
            staging = app_root / ".app-update" / "staging-1.4.1"
            staging.mkdir(parents=True)
            old_exe = app_root / "Stream Translator.exe"
            old_exe.write_bytes(b"old executable")
            (app_root / "config.yaml").write_text("terminology:\n  glossary_list: []\ntranscription:\n  asr_correction_rules: []\n", encoding="utf-8")
            (staging / "Stream Translator.exe").write_bytes(b"not a valid executable")
            (staging / "app-update-build.json").write_text(json.dumps({
                "schema": 1, "profile": "cuda", "version": "1.4.1",
            }), encoding="utf-8")
            plan = app_root / ".app-update" / "apply-plan.json"
            plan.write_text(json.dumps({
                "schema": 1, "app_root": str(app_root), "staging": str(staging),
                "version": "1.4.1", "profile": "cuda", "executable": old_exe.name,
                "parent_pid": 99999999,
            }), encoding="utf-8")
            errors=[]; worker=Worker(plan); worker.failed.connect(errors.append); worker.run()
            self.assertTrue(errors)
            self.assertEqual(old_exe.read_bytes(), b"old executable")
            self.assertIn("glossary_list",(app_root / "config.yaml").read_text(encoding="utf-8"))
            self.assertTrue(any((app_root/".app-update"/"user-backups").glob("before-1.4.1-*")))


if __name__ == "__main__":
    unittest.main()
