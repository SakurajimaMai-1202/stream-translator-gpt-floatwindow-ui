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
