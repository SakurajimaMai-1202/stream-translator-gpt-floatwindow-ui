import hashlib
import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from manual_update import prepare_package
from updater import ALLOWED, Worker, installation_processes


@pytest.fixture
def local_package(tmp_path):
    root = tmp_path / "install"
    root.mkdir()
    (root / "Stream Translator.exe").write_bytes(b"old")
    (root / "config.yaml").write_text("terminology: {}", encoding="utf-8")
    runtime = root / "_runtime"
    runtime.mkdir()
    (runtime / "runtime-version.json").write_text(json.dumps({"profile": "cpu", "app_version": "1.4.9"}))
    manifest = {"schema": 2, "profile": "cpu", "version": "1.4.10", "update_mode": "app_only",
                "minimum_upgradable_version": "1.3.11"}
    archive = tmp_path / "update.zip"

    def build(extra=None, changes=None):
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("app-update-build.json", json.dumps(manifest | (changes or {})))
            bundle.writestr("Stream Translator.exe", b"new")
            bundle.writestr("StreamTranslatorUpdater.exe", b"updater")
            for name, value in (extra or {}).items():
                entry = zipfile.ZipInfo(name)
                entry.filename = name  # Preserve backslashes on Windows for the malicious-path test.
                bundle.writestr(entry, value)
        return archive
    return root, build


def test_local_zip_prepares_valid_plan_and_preserves_installation(local_package):
    root, build = local_package
    plan = prepare_package(build(), root, ALLOWED)
    assert Worker.validate_plan(plan)[-1] == "app_only"
    assert (root / "Stream Translator.exe").read_bytes() == b"old"
    assert (root / "config.yaml").read_text() == "terminology: {}"


def test_split_package_reassembles_and_rejects_gap(local_package):
    root, build = local_package
    archive = build()
    data = archive.read_bytes()
    first = archive.with_name("update.zip.part01")
    second = archive.with_name("update.zip.part02")
    first.write_bytes(data[:len(data)//2])
    second.write_bytes(data[len(data)//2:])
    Worker.validate_plan(prepare_package(first, root, ALLOWED))
    second.rename(second.with_name("update.zip.part03"))
    with pytest.raises(RuntimeError, match="缺少"):
        prepare_package(first, root, ALLOWED)


@pytest.mark.parametrize("name", ["../outside", "_internal/../../outside", "config.yaml", "_internal/C:bad", "_internal/CON.txt"])
def test_rejects_protected_or_unsafe_paths(local_package, name):
    root, build = local_package
    with pytest.raises(RuntimeError, match="路徑"):
        prepare_package(build({name: b"bad"}), root, ALLOWED)
    assert (root / "Stream Translator.exe").read_bytes() == b"old"


@pytest.mark.parametrize("changes", [{"profile": "cuda"}, {"version": "1.4.8"},
                                       {"minimum_upgradable_version": "1.5.0"}, {"requires_full_install": True},
                                       {"schema": 1, "update_mode": "runtime_replace"}])
def test_rejects_incompatible_package(local_package, changes):
    root, build = local_package
    extra = {"_runtime/python.exe": b"runtime"} if changes.get("schema") == 1 else {}
    with pytest.raises(RuntimeError):
        prepare_package(build(extra, changes), root, ALLOWED)


def test_checksums_pass_then_reject_corruption(local_package):
    root, build = local_package
    archive = build()
    checksum = archive.parent / "SHA256SUMS-v1.4.10.txt"
    checksum.write_text(hashlib.sha256(archive.read_bytes()).hexdigest() + "  update.zip\n")
    Worker.validate_plan(prepare_package(archive, root, ALLOWED))
    archive.write_bytes(archive.read_bytes() + b"corrupted")
    with pytest.raises(RuntimeError, match="SHA-256"):
        prepare_package(archive, root, ALLOWED)


def test_process_query_detects_this_python_installation():
    if sys.platform != "win32":
        pytest.skip("Windows process query")
    # Query an unrelated directory; this must not report arbitrary Python processes.
    assert installation_processes(Path(__file__).parent) == []
