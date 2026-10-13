import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

APP_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP_DIR))
from backend.core import app_update_manager as updates
from updater import Worker


class RuntimeContractTest(unittest.TestCase):
    def test_staging_and_updater_enforce_runtime_baseline(self):
        cases = [
            ("app_only", "1.4.9", "cuda", True, True),
            ("app_only", "1.4.8", "cuda", True, False),
            ("app_only", "1.4.9", "cpu", True, False),
            ("app_only", "1.4.9", "cuda", False, False),
            ("app_only", None, "cuda", True, False),
            ("runtime_replace", "1.4.10", "cuda", True, True),
            ("runtime_replace", "1.4.8", "cuda", True, False),
        ]
        for mode, runtime_version, profile, has_omnivad, accepted in cases:
            with self.subTest(case=(mode, runtime_version, profile, has_omnivad)):
                with tempfile.TemporaryDirectory(dir=APP_DIR) as temp:
                    root = Path(temp)
                    staging = root / ".app-update/staging"
                    staging.mkdir(parents=True)
                    manifest = dict(schema=2, profile="cuda", version="1.4.10",
                                    update_mode=mode, minimum_runtime_version="1.4.9")
                    (staging / "app-update-build.json").write_text(json.dumps(manifest))
                    (staging / "Stream Translator.exe").touch()
                    runtime = (staging if mode == "runtime_replace" else root) / "_runtime"
                    runtime.mkdir()
                    (runtime / "python.exe").touch()
                    if runtime_version:
                        (runtime / "runtime-version.json").write_text(json.dumps(
                            dict(profile=profile, app_version=runtime_version)))
                    if has_omnivad:
                        package = runtime / "Lib/site-packages/omnivad"
                        package.mkdir(parents=True)
                        (package / "__init__.py").touch()
                    plan_path = root / "plan.json"
                    plan_path.write_text(json.dumps(dict(schema=2, profile="cuda",
                        version="1.4.10", app_root=str(root), staging=str(staging), update_mode=mode)))
                    with mock.patch.object(updates, "get_app_root", return_value=root):
                        manager = updates.AppUpdateManager()
                        manager._set(profile="cuda", current_version="1.4.10", latest_version="1.4.10")
                        for check in (lambda: manager._validate_staging(staging),
                                      lambda: Worker.validate_plan(plan_path)):
                            if accepted:
                                check()
                            else:
                                with self.assertRaises(RuntimeError):
                                    check()


    def test_schema_validation_is_shared_and_bom_tolerant(self):
        from update_runtime_contract import read_update_json, validate_update_schema
        for schema in (None, True, "2", 2.5, [], {}, 3):
            with self.subTest(schema=schema), self.assertRaisesRegex(RuntimeError, "schema"):
                validate_update_schema(dict(schema=schema, update_mode="app_only"))
        with self.assertRaisesRegex(RuntimeError, "requires update_mode"):
            validate_update_schema(dict(schema=2))
        self.assertEqual(validate_update_schema(dict(schema=1)), 1)
        self.assertEqual(read_update_json(b'\xef\xbb\xbf{"schema": 1}'), {"schema": 1})
        for payload in (b'[]', b'null', b'{'):
            with self.assertRaises(ValueError):
                read_update_json(payload)

    def test_manifest_schema_checked_by_both_consumers(self):
        for schema, mode, accepted in [(1, None, True), (2, None, False),
                                      (2, "app_only", True), (99, "app_only", False)]:
            with self.subTest(schema=schema, mode=mode), tempfile.TemporaryDirectory(dir=APP_DIR) as temp:
                root = Path(temp)
                staging = root / ".app-update/staging"
                staging.mkdir(parents=True)
                (staging / "Stream Translator.exe").touch()
                manifest = dict(schema=schema, profile="cuda", version="1.4.10")
                if mode:
                    manifest["update_mode"] = mode
                (staging / "app-update-build.json").write_text(json.dumps(manifest), encoding="utf-8-sig")
                plan = root / "plan.json"
                plan.write_text(json.dumps(dict(schema=2, update_mode="app_only", profile="cuda",
                    version="1.4.10", app_root=str(root), staging=str(staging))), encoding="utf-8-sig")
                with mock.patch.object(updates, "get_app_root", return_value=root):
                    manager = updates.AppUpdateManager()
                    manager._set(profile="cuda", latest_version="1.4.10")
                    for check in (lambda: manager._validate_staging(staging), lambda: Worker.validate_plan(plan)):
                        if accepted:
                            check()
                        else:
                            with self.assertRaisesRegex(RuntimeError, "schema"):
                                check()
