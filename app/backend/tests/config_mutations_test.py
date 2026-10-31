import asyncio
import io
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, get_ident
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import HTTPException, UploadFile
from starlette.requests import Request

from backend.api import config as api
from backend.core.config_manager import ConfigManager


def request():
    return Request({"type": "http", "headers": []})


def test_a1_a2_preset_handlers_only_mutate_named_key(tmp_path, monkeypatch):
    from backend.api import llama
    manager = ConfigManager(tmp_path / "config.yaml")
    other = ConfigManager(manager.config_path)
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    other.update_config({"llama": {"n_ctx": 12345, "custom_presets": {
        "keep": {"model_path": "keep.gguf"}, "edit": {"obsolete": True}}}})
    # Handlers must not read a snapshot, even one from the same manager.
    monkeypatch.setattr(manager, "get_config", lambda: pytest.fail("stale snapshot read"))
    asyncio.run(llama.save_custom_preset("edit", llama.ServerConfig(model_path="new.gguf")))
    saved = ConfigManager(manager.config_path).get_config()["llama"]
    assert saved["n_ctx"] == 12345
    assert "obsolete" not in saved["custom_presets"]["edit"]
    asyncio.run(llama.delete_custom_preset("edit"))
    reloaded = ConfigManager(manager.config_path).get_config()["llama"]
    assert reloaded["custom_presets"] == {"keep": {"model_path": "keep.gguf"}}
    assert reloaded["n_ctx"] == 12345
    with pytest.raises(HTTPException) as error:
        asyncio.run(llama.delete_custom_preset("edit"))
    assert error.value.status_code == 404


def test_a2_waiting_key_mutation_reads_latest_disk(tmp_path):
    holder = ConfigManager(tmp_path / "config.yaml")
    writer = ConfigManager(holder.config_path)
    started = Event()

    def mutate():
        started.set()
        writer.update_key(("llama", "custom_presets", "new"), {"n_ctx": 2048})

    with ThreadPoolExecutor(max_workers=1) as pool:
        with holder._config_lock():
            pending = pool.submit(mutate)
            assert started.wait(5)
            current = holder._read_current_config()
            current["llama"]["n_ctx"] = 6789
            current["llama"]["custom_presets"]["other"] = {"n_ctx": 100}
            holder._save(current)
        pending.result(timeout=5)
    saved = ConfigManager(holder.config_path).get_config()["llama"]
    assert saved["n_ctx"] == 6789
    assert set(saved["custom_presets"]) == {"new", "other"}


def test_a3_explicit_replace_delete_preserves_partial_merge(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_config({"extension": {"first": {"a": 1, "b": 2}, "other": 3}})
    manager.update_config({"extension": {"first": {"a": 4}}})
    assert manager.get_config()["extension"]["first"] == {"a": 4, "b": 2}
    manager.update_key(("extension", "first"), {"c": 5})
    manager.update_key(("extension", "other"), delete=True)
    assert ConfigManager(manager.config_path).get_config()["extension"] == {"first": {"c": 5}}


@pytest.mark.parametrize("initial", [True, False])
@pytest.mark.parametrize("bad", [b"llama: [", b"- scalar", b"null", b"llama: 42", b"translation: []", b"input: {cookies_by_site: false}"])
def test_a4_a6_corrupt_config_is_preserved_and_saves_recover(tmp_path, initial, bad):
    path = tmp_path / "config.yaml"
    manager = None if initial else ConfigManager(path)
    path.write_bytes(bad)
    if initial:
        manager = ConfigManager(path)
    manager.update_config({"general": {"log_level": "DEBUG"}})
    backups = list(tmp_path.glob("config.yaml.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_bytes() == bad
    assert ConfigManager(path).get_config()["general"]["log_level"] == "DEBUG"


def test_a4_reset_backs_up_exact_bytes(tmp_path):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.config_path.write_bytes(b"# retain comment\nllama: [broken")
    before = manager.config_path.read_bytes()
    manager.reset_to_defaults()
    assert next(tmp_path.glob("config.yaml.bak-*")).read_bytes() == before
    assert isinstance(yaml.safe_load(manager.config_path.read_bytes()), dict)


@pytest.mark.parametrize("upload", [False, True])
def test_a5_import_replaces_settings_preserving_secret_contract(tmp_path, monkeypatch, upload):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_config({"extension": {"old": True}, "llama": {"n_ctx": 777,
        "custom_presets": {"old": {"n_ctx": 99}}},
        "translation": {"openai_api_key": "private-secret"}})
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    publisher = AsyncMock()
    monkeypatch.setattr(api, "publish_app_event", publisher)
    data = {"general": {"log_level": "DEBUG"}}
    if upload:
        asyncio.run(api.import_config_file(request(), UploadFile(file=io.BytesIO(yaml.safe_dump(data).encode()))))
    else:
        asyncio.run(api.import_config({"content": yaml.safe_dump(data)}, request()))
    saved = manager.get_config()
    assert "extension" not in saved
    assert saved["llama"]["custom_presets"] == {}
    assert saved["llama"]["n_ctx"] == manager.DEFAULT_CONFIG["llama"]["n_ctx"]
    assert saved["translation"]["openai_api_key"] == "private-secret"
    assert "private-secret" not in str(publisher.await_args)


@pytest.mark.parametrize("data", [{"llama": []}, {"translation": None}])
def test_a6_invalid_import_is_400_without_writing(tmp_path, monkeypatch, data):
    manager = ConfigManager(tmp_path / "config.yaml")
    before = manager.config_path.read_bytes()
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    with pytest.raises(HTTPException) as error:
        asyncio.run(api.import_config(data, request()))
    assert error.value.status_code == 400
    assert manager.config_path.read_bytes() == before


def test_a7_creation_and_reset_save_inside_lock(tmp_path, monkeypatch):
    original_lock = ConfigManager._config_lock
    original_save = ConfigManager._save
    active = []

    @contextmanager
    def tracked_lock(self):
        with original_lock(self):
            active.append(True)
            try:
                yield
            finally:
                active.pop()

    def checked_save(self, config, **kwargs):
        assert active
        original_save(self, config, **kwargs)

    monkeypatch.setattr(ConfigManager, "_config_lock", tracked_lock)
    monkeypatch.setattr(ConfigManager, "_save", checked_save)
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.reset_to_defaults()


def test_a8_lock_has_bounded_wait(tmp_path, monkeypatch):
    holder = ConfigManager(tmp_path / "config.yaml")
    writer = ConfigManager(holder.config_path)
    monkeypatch.setattr(writer, "LOCK_TIMEOUT_SECONDS", 0.05)
    with holder._config_lock(), ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(writer.update_config, {"general": {"log_level": "DEBUG"}})
        with pytest.raises(TimeoutError, match="configuration lock"):
            future.result(timeout=2)


@pytest.mark.parametrize("operation", ["section", "reset", "import", "upload"])
def test_a8_api_disk_mutations_run_off_event_loop(tmp_path, monkeypatch, operation):
    manager = ConfigManager(tmp_path / "config.yaml")
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    monkeypatch.setattr(api, "publish_app_event", AsyncMock())
    loop_thread = get_ident()
    original = manager._save

    def check(config):
        assert get_ident() != loop_thread
        original(config)

    monkeypatch.setattr(manager, "_save", check)
    if operation == "section":
        call = api.update_section("general", {"log_level": "DEBUG"}, request())
    elif operation == "reset":
        call = api.reset_config(request())
    elif operation == "upload":
        call = api.import_config_file(request(), UploadFile(file=io.BytesIO(b"general: {}")))
    else:
        call = api.import_config({"general": {}}, request())
    asyncio.run(call)


@pytest.mark.parametrize("method", ["update_config", "replace_config"])
@pytest.mark.parametrize("masked", [False, True])
def test_secret_rotation_before_mutation_lock_is_not_overwritten(tmp_path, monkeypatch, method, masked):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_config({"translation": {"openai_api_key": "old-private-key"}})
    other = ConfigManager(manager.config_path)
    entered = Event()
    rotated = Event()
    original = getattr(manager, method)

    def delayed_mutation(data):
        # The API has handed off the request, but no mutation lock is held yet.
        entered.set()
        assert rotated.wait(5)
        return original(data)

    monkeypatch.setattr(manager, method, delayed_mutation)
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    monkeypatch.setattr(api, "publish_app_event", AsyncMock())
    data = {"translation": {"history_size": 7}}
    if masked:
        from backend.core.config_secrets import mask_secrets
        data["translation"]["openai_api_key"] = mask_secrets(
            {"openai_api_key": "old-private-key"})["openai_api_key"]

    def request_write():
        if method == "replace_config":
            return asyncio.run(api.import_config(data, request()))
        return asyncio.run(api.update_full_config(data, request()))

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(request_write)
        try:
            assert entered.wait(5)
            other.update_config({"translation": {"openai_api_key": "rotated-private-key"}})
        finally:
            rotated.set()
        assert pending.result(timeout=5)["success"]
    saved = ConfigManager(manager.config_path).get_config()["translation"]
    assert saved["openai_api_key"] == "rotated-private-key"
    assert saved["history_size"] == 7


@pytest.mark.parametrize("data", [
    {"translation": {"custom_models": None}},
    {"translation": {"custom_models": [None]}},
    {"translation": {"custom_models": ["invalid"]}},
    {"translation": {"custom_models": [{"name": []}]}},
    {"translation": {"custom_models": [{"api_url": {}}]}},
    {"transcription": {"filters": None}},
    {"llama": {"custom_model_series": {}}},
])
@pytest.mark.parametrize("operation", ["update", "import", "upload", "recovery"])
def test_invalid_list_shapes_never_persist(tmp_path, monkeypatch, data, operation):
    manager = ConfigManager(tmp_path / "config.yaml")
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    before = manager.config_path.read_bytes()
    if operation == "recovery":
        bad = yaml.safe_dump(data).encode()
        manager.config_path.write_bytes(bad)
        manager = ConfigManager(manager.config_path)
        assert next(tmp_path.glob("config.yaml.corrupt-*")).read_bytes() == bad
        assert isinstance(manager.get_config()["translation"]["custom_models"], list)
        return
    with pytest.raises(HTTPException) as error:
        if operation == "update":
            asyncio.run(api.update_full_config(data, request()))
        elif operation == "upload":
            upload = UploadFile(file=io.BytesIO(yaml.safe_dump(data).encode()))
            asyncio.run(api.import_config_file(request(), upload))
        else:
            asyncio.run(api.import_config(data, request()))
    assert error.value.status_code == 400
    assert manager.config_path.read_bytes() == before


@pytest.mark.parametrize("endpoint", ["config", "llama_presets"])
def test_get_config_does_not_block_loop_while_writer_holds_lock(tmp_path, monkeypatch, endpoint):
    reader = ConfigManager(tmp_path / "config.yaml")
    writer = ConfigManager(reader.config_path)
    monkeypatch.setattr(api, "get_config_manager", lambda: reader)
    written = Event()
    reading = Event()
    heartbeat = Event()
    original_lock = reader._config_lock

    @contextmanager
    def observed_lock():
        reading.set()
        with original_lock():
            yield

    monkeypatch.setattr(reader, "_config_lock", observed_lock)

    def hold_writer_lock():
        with writer._config_lock():
            config = writer._read_current_config()
            config["general"]["log_level"] = "DEBUG"
            config["llama"]["custom_presets"]["latest"] = {"n_ctx": 1234}
            writer._save(config)
            written.set()
            # Bounded wait releases the lock even if the old synchronous GET
            # blocks the loop. The returned flag then makes the test fail.
            return heartbeat.wait(3)

    async def read_with_heartbeat():
        from backend.api import llama
        read = api.get_config if endpoint == "config" else llama.get_custom_presets
        pending = asyncio.create_task(read())
        try:
            assert await asyncio.to_thread(reading.wait, 2)
            await asyncio.sleep(0)
            heartbeat.set()
            return await pending
        finally:
            heartbeat.set()
            await pending

    with ThreadPoolExecutor(max_workers=1) as pool:
        held = pool.submit(hold_writer_lock)
        try:
            assert written.wait(5)
            result = asyncio.run(read_with_heartbeat())
            assert held.result(timeout=5), "GET blocked the event loop behind the file lock"
        finally:
            heartbeat.set()
    if endpoint == "config":
        assert result["data"]["general"]["log_level"] == "DEBUG"
    else:
        assert result == {"latest": {"n_ctx": 1234}}


@pytest.mark.parametrize("operation", ["get", "status", "export", "health", "connection"])
def test_async_config_readers_lookup_manager_off_loop(tmp_path, monkeypatch, operation):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_config({"translation": {"backend": "none"}})
    loop_thread = get_ident()

    def lookup():
        assert get_ident() != loop_thread
        return manager

    monkeypatch.setattr(api, "get_config_manager", lookup)
    if operation == "get":
        asyncio.run(api.get_config())
    elif operation == "status":
        asyncio.run(api.get_config_status())
    elif operation == "export":
        asyncio.run(api.export_config())
    elif operation == "health":
        with pytest.raises(HTTPException) as error:
            asyncio.run(api.check_hy_mt2_backend())
        assert error.value.status_code == 400
    else:
        result = asyncio.run(api.test_connection(api.TestConnectionRequest(backend="gpt", api_key="")))
        assert not result["success"]


@pytest.mark.parametrize("upload", [False, True])
@pytest.mark.parametrize("masked", [False, True])
@pytest.mark.parametrize("stored_key", ["", None, "stored-transcription-key"])
def test_import_restores_exact_stored_secrets_before_legacy_migration(
        tmp_path, monkeypatch, upload, masked, stored_key):
    from backend.core.config_secrets import mask_secrets, omit_secrets

    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_config({
        "general": {"openai_api_key": "legacy-general-key"},
        "transcription": {"openai_api_key": stored_key},
        "translation": {"openai_api_key": "stored-translation-key"},
    })
    original = manager.get_config()
    incoming = (mask_secrets if masked else omit_secrets)(original)
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    monkeypatch.setattr(api, "publish_app_event", AsyncMock())

    if upload:
        file = UploadFile(file=io.BytesIO(yaml.safe_dump(incoming).encode()))
        asyncio.run(api.import_config_file(request(), file))
    else:
        asyncio.run(api.import_config(incoming, request()))

    assert manager.get_config() == original
    # Inspect persisted values directly: constructing another manager would run
    # startup migration and obscure whether import preserved the stored keys.
    persisted = yaml.safe_load(manager.config_path.read_bytes())
    assert persisted["transcription"]["openai_api_key"] == stored_key
    assert persisted["general"]["openai_api_key"] == "legacy-general-key"
    assert persisted["translation"]["openai_api_key"] == "stored-translation-key"


@pytest.mark.parametrize("upload", [False, True])
@pytest.mark.parametrize("marker", [None, False])
def test_import_legacy_visibility_survives_restart(tmp_path, monkeypatch, upload, marker):
    manager = ConfigManager(tmp_path / "config.yaml")
    monkeypatch.setattr(api, "get_config_manager", lambda: manager)
    monkeypatch.setattr(api, "publish_app_event", AsyncMock())
    incoming = {
        "subtitle_settings": {"showOriginal": False, "showTranslated": False},
        "translation": {"backend": "localllm", "gpt_base_url": ""},
    }
    if marker is not None:
        incoming["subtitle_settings"]["_visibility_defaults_v2"] = marker
    if upload:
        file = UploadFile(file=io.BytesIO(yaml.safe_dump(incoming).encode()))
        asyncio.run(api.import_config_file(request(), file))
    else:
        asyncio.run(api.import_config(incoming, request()))

    persisted = yaml.safe_load(manager.config_path.read_bytes())
    assert persisted["subtitle_settings"]["_visibility_defaults_v2"] is True
    assert persisted["subtitle_settings"]["showOriginal"] is False
    assert persisted["translation"]["backend"] == "llama"
    assert persisted["translation"]["gpt_base_url"] == "https://api.openai.com/v1"
    restarted = ConfigManager(manager.config_path)
    restarted.update_config({"general": {"log_level": "DEBUG"}})
    settings = restarted.get_config()["subtitle_settings"]
    assert settings["showOriginal"] is False
    assert settings["showTranslated"] is False
