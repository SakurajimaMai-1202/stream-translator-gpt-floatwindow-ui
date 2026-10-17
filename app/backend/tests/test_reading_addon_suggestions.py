import asyncio
import hashlib
import io
import json
import zipfile

import pytest

from backend.core import reading_addon_installer as addon
from backend.api import terminology


@pytest.fixture
def wheel(monkeypatch, tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("janome/__init__.py", "")
        archive.writestr("janome/tokenizer.py", "# fake tokenizer")
        archive.writestr("Janome-0.5.0.dist-info/METADATA", "Version: 0.5.0")
        archive.writestr("unrelated.txt", "must not extract")
    data = buffer.getvalue()
    monkeypatch.setattr(addon, "get_app_root", lambda: tmp_path)
    monkeypatch.setattr(addon, "SIZE", len(data))
    monkeypatch.setattr(addon, "SHA256", hashlib.sha256(data).hexdigest())

    class FakeDownloader:
        def __init__(self, progress):
            self.progress = progress

        def download(self, url, destination):
            assert url == addon.URL
            destination.write_bytes(data)
            self.progress(len(data), len(data))

    monkeypatch.setattr(addon, "HttpDownloader", FakeDownloader)
    return addon.ReadingAddonInstaller()


def test_install_and_status(wheel):
    assert wheel.status() == {"installed": False, "version": "0.5.0", "size_bytes": None,
                              "state": "idle", "progress": 0.0, "error": None}
    wheel.install()
    assert wheel.status() == {"installed": True, "version": "0.5.0", "size_bytes": addon.SIZE,
                              "state": "idle", "progress": 1.0, "error": None}
    assert not (addon.install_directory() / "unrelated.txt").exists()
    assert len(list(addon.install_directory().parent.iterdir())) == 1
    assert wheel.remove()["installed"] is False


@pytest.mark.parametrize("mismatch", ["SHA256", "SIZE"])
def test_mismatch_leaves_no_install(wheel, monkeypatch, mismatch):
    monkeypatch.setattr(addon, mismatch, "0" * 64 if mismatch == "SHA256" else addon.SIZE + 1)
    wheel.install()
    assert wheel.status()["state"] == "error"
    assert mismatch.replace("SIZE", "size").replace("SHA256", "SHA-256") in wheel.status()["error"]
    assert not addon.install_directory().exists()
    assert list(addon.install_directory().parent.iterdir()) == []


def test_translator_environment_only_complete_install(wheel):
    env = {"STREAM_TRANSLATOR_READING_ADDON": "inherited-stale-path"}
    addon.apply_reading_addon_environment(env)
    assert "STREAM_TRANSLATOR_READING_ADDON" not in env
    wheel.install()
    addon.apply_reading_addon_environment(env)
    assert env["STREAM_TRANSLATOR_READING_ADDON"] == str(addon.install_directory())
    (addon.install_directory() / "janome/tokenizer.py").unlink()
    addon.apply_reading_addon_environment(env)
    assert "STREAM_TRANSLATOR_READING_ADDON" not in env


def test_begin_idempotent_while_running(wheel, monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            started.append(True)

    monkeypatch.setattr(addon.threading, "Thread", FakeThread)
    assert wheel.begin()["state"] == "downloading"
    assert wheel.begin()["state"] == "downloading"
    assert len(started) == 1
    with pytest.raises(RuntimeError):
        wheel.remove()


def test_suggestions_filters_and_delete(monkeypatch, tmp_path):
    from backend.core.hy_mt2_glossary_presets import PRESET_ASR_VARIANTS
    builtin = next(alias for variants in PRESET_ASR_VARIANTS.values()
                   for aliases in variants.values() for alias in aliases)
    monkeypatch.setenv("STREAM_TRANSLATOR_ASR_CORRECTION_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(terminology, "is_installed", lambda: True)
    monkeypatch.setattr(terminology, "_read_config", lambda: {
        "transcription": {"asr_correction_learning_enabled": True},
        "terminology": {"ignored_alias_suggestions": [{"alias": "ignored", "canonical": "target"}],
                        "glossary_list": [{"original": "original", "aliases": ["alias"]}]}})
    records = [{"alias": alias, "canonical": "target", "count": count, "best_score": 1.0,
                "reading_match": True, "examples": ["example"], "asr_engines": ["fake"]}
               for alias, count in [("ignored", 2), ("original", 2), ("alias", 2),
                                    (builtin, 2), ("singleton", 1), ("keep", 3)]]
    terminology.suggestions_path().write_text(json.dumps({"records": records,
        "pending_records": [records[-1]], "updated_at": "now"}), encoding="utf-8")
    response = asyncio.run(terminology.get_alias_suggestions())
    assert response == {"log_enabled": True, "reading_enabled": True, "updated_at": "now",
                        "suggestions": [records[-1]]}
    asyncio.run(terminology.delete_alias_suggestions())
    cleared = json.loads(terminology.suggestions_path().read_text(encoding="utf-8"))
    assert cleared["version"] == 2
    assert cleared["cleared_at"]
    assert cleared["records"] == cleared["pending_records"] == []
    assert asyncio.run(terminology.get_alias_suggestions())["suggestions"] == []


def test_routes_share_config_registration():
    from backend.api.config import router
    paths = {route.path for route in router.routes}
    assert "/config/hy-mt2-glossary-presets" in paths
    assert "/terminology/alias-suggestions" in paths
    assert "/terminology/reading-addon/install" in paths


def test_incomplete_install_is_replaced(wheel):
    target = addon.install_directory()
    target.mkdir(parents=True)
    (target / ".complete.json").write_text("{}", encoding="utf-8")
    assert wheel.status()["installed"] is False
    wheel.install()
    assert wheel.status()["installed"] is True


def test_remove_quarantines_before_cleanup(wheel, monkeypatch):
    wheel.install()
    cleanup = addon._remove_scratch
    leftovers = []
    def blocked(path):
        assert not addon.install_directory().exists()
        assert path.name.startswith(".janome-removing-")
        leftovers.append(path)
    monkeypatch.setattr(addon, "_remove_scratch", blocked)
    assert wheel.remove()["installed"] is False
    assert leftovers[0].exists()
    monkeypatch.setattr(addon, "_remove_scratch", cleanup)
    wheel.install()
    assert wheel.status()["installed"] is True
    assert not leftovers[0].exists()


def test_remove_oserror_is_conflict(wheel, monkeypatch):
    wheel.install()
    def blocked(*args):
        raise PermissionError("locked")
    monkeypatch.setattr(addon.os, "rename", blocked)
    with pytest.raises(RuntimeError, match="Unable to remove"):
        wheel.remove()
    assert wheel.status()["state"] == "error"
    assert wheel.status()["installed"] is True
    monkeypatch.setattr(terminology, "reading_addon_installer", wheel)
    from backend.core import translator
    monkeypatch.setattr(translator, "active_translations", {})
    with pytest.raises(terminology.HTTPException) as exc:
        asyncio.run(terminology.delete_reading_addon())
    assert exc.value.status_code == 409


def test_malformed_suggestions_are_tolerated(monkeypatch, tmp_path):
    monkeypatch.setenv("STREAM_TRANSLATOR_ASR_CORRECTION_LOG_DIR", str(tmp_path))
    monkeypatch.setattr(terminology, "_read_config", lambda: {"terminology": {
        "ignored_alias_suggestions": None,
        "glossary_list": [None, 42, {"aliases": 42}, {"aliases": {"bad": True}}]}})
    records = [None, {}, {"alias": [], "canonical": "標準", "count": 2},
               {"alias": "候補", "canonical": "標準", "count": 2, "examples": None},
               {"alias": "別候補", "canonical": "標準", "count": 2, "examples": 42}]
    terminology.suggestions_path().write_text(json.dumps({"records": records}), encoding="utf-8")
    result = terminology.read_suggestions()["suggestions"]
    assert len(result) == 2
    assert all(row["examples"] == [] for row in result)
