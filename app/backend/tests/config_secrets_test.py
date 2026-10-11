import asyncio
import copy
import io
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml
from fastapi import Request, UploadFile

from backend.api import config as config_api
from backend.core.config_manager import ConfigManager
from backend.core.config_secrets import mask_secrets, omit_secrets, restore_masked_secrets


SECRET = "sk-private-key-12345678"
MODEL_SECRET = "custom-private-key-87654321"


@pytest.fixture
def config_context(tmp_path, monkeypatch):
    manager = ConfigManager(tmp_path / "config.yaml")
    manager.update_config({
        "general": {"openai_api_key": SECRET, "google_api_key": ""},
        "input": {"cookies": "session-private-cookie", "cookies_by_site": {
            "youtube": "youtube-private-cookie", "empty": "", "unset": None,
        }},
        "translation": {"openai_api_key": SECRET, "google_api_key": None,
                        "translation_max_output_tokens": 128,
                        "custom_models": [
                            {"name": "first", "api_key": MODEL_SECRET, "model_name": "model-1"},
                            {"name": "second", "api_key": "second-private-key", "model_name": "model-2"},
                        ]},
        "output": {"cqhttp_token": "cqhttp-private-token"},
        "output_notification": {"telegram_bot_token": "telegram-private-token"},
    })
    publisher = AsyncMock()
    monkeypatch.setattr(config_api, "get_config_manager", lambda: manager)
    monkeypatch.setattr(config_api, "publish_app_event", publisher)
    request = Request({"type": "http", "headers": [(b"x-client-id", b"test-client")]})
    return manager, request, publisher


def test_mask_secrets_deep_copy_and_explicit_fields():
    original = {
        "translation": {"openai_api_key": SECRET, "google_api_key": "", "api_key": None,
                        "translation_max_output_tokens": 128,
                        "hy_mt2_lm_studio_api_key": SECRET,
                        "hy_mt2_llama_cpp_api_key": SECRET,
                        "index_translate_lm_studio_api_key": SECRET,
                        "index_translate_llama_cpp_api_key": SECRET,
                        "custom_models": [{"name": "first", "api_key": "short"}]},
        "input": {"cookies": "private-cookie", "cookies_by_site": {
            "youtube": "private-site-cookie", "empty": "", "unset": None,
        }},
        "output": {"cqhttp_token": "private-token"},
        "output_notification": {"telegram_bot_token": "private-bot-token",
                                "discord_webhook_url": "https://discord.com/api/webhooks/private/token"},
    }
    before = copy.deepcopy(original)
    masked = mask_secrets(original)
    assert original == before
    assert masked["translation"]["openai_api_key"].startswith("••••")
    assert SECRET not in str(masked)
    assert masked["translation"]["google_api_key"] == ""
    assert masked["translation"]["api_key"] is None
    assert masked["translation"]["translation_max_output_tokens"] == 128
    assert masked["translation"]["custom_models"][0]["api_key"] == "••••••••"
    assert masked["input"]["cookies"].startswith("••••")
    assert masked["input"]["cookies_by_site"]["youtube"].startswith("••••")
    assert masked["input"]["cookies_by_site"]["empty"] == ""
    assert masked["input"]["cookies_by_site"]["unset"] is None
    assert masked["output"]["cqhttp_token"].startswith("••••")
    assert masked["output_notification"]["telegram_bot_token"].startswith("••••")
    assert masked["output_notification"]["discord_webhook_url"].startswith("••••")
    for field in ("hy_mt2_lm_studio_api_key", "hy_mt2_llama_cpp_api_key",
                  "index_translate_lm_studio_api_key", "index_translate_llama_cpp_api_key"):
        assert masked["translation"][field].startswith("••••")
    masked["translation"]["custom_models"][0]["name"] = "changed"
    assert original == before


def test_get_config_returns_masked(config_context):
    manager, _, _ = config_context
    result = asyncio.run(config_api.get_config())
    assert result["success"] is True
    assert result["data"] == mask_secrets(manager.get_config())
    assert manager.get_config()["general"]["openai_api_key"] == SECRET


@pytest.mark.parametrize("operation", ["put", "patch"])
def test_masked_save_preserves_secret_and_masks_response_and_event(config_context, operation):
    manager, request, publisher = config_context
    incoming = {"openai_api_key": mask_secrets({"openai_api_key": SECRET})["openai_api_key"]}
    if operation == "put":
        result = asyncio.run(config_api.update_full_config({"general": incoming}, request))
        returned = result["data"]["general"]
    else:
        result = asyncio.run(config_api.update_section("general", incoming, request))
        returned = result["data"]
    assert manager.get_config()["general"]["openai_api_key"] == SECRET
    assert returned["openai_api_key"].startswith("••••")
    event_name, payload = publisher.await_args.args
    assert event_name == "config.updated"
    assert payload["config"] == mask_secrets(manager.get_config())
    assert payload["source_client_id"] == "test-client"


def test_put_new_secret_updates_storage(config_context):
    manager, request, _ = config_context
    new_secret = "sk-new-private-key-9999"
    result = asyncio.run(config_api.update_full_config({"general": {"openai_api_key": new_secret}}, request))
    assert manager.get_config()["general"]["openai_api_key"] == new_secret
    assert result["data"]["general"]["openai_api_key"] == mask_secrets({"api_key": new_secret})["api_key"]


def test_custom_models_restore_by_name_instead_of_position(config_context):
    manager, request, _ = config_context
    models = mask_secrets(manager.get_config())["translation"]["custom_models"]
    models.reverse()
    models.append({"name": "new-model", "api_key": "••••unknown"})
    asyncio.run(config_api.update_section("translation", {"custom_models": models}, request))
    saved = {item["name"]: item["api_key"] for item in manager.get_config()["translation"]["custom_models"]}
    assert saved == {"first": MODEL_SECRET, "second": "second-private-key", "new-model": ""}


def test_restore_mask_prefix_and_cookie_values():
    current = {"api_key": SECRET, "cookies_by_site": {"youtube": "private-cookie"}}
    incoming = {"api_key": "••••stale", "cookies_by_site": {"youtube": "••••stale", "new": "••••unknown"}}
    before = copy.deepcopy(incoming)
    restored = restore_masked_secrets(incoming, current)
    assert incoming == before
    assert restored == {"api_key": SECRET, "cookies_by_site": {"youtube": "private-cookie", "new": ""}}


def test_export_omits_secrets_by_default_and_includes_with_flag(config_context):
    manager, _, _ = config_context
    exported = yaml.safe_load(asyncio.run(config_api.export_config()).body)
    assert exported == omit_secrets(manager.get_config())
    assert "openai_api_key" not in exported["general"]
    assert "cookies_by_site" not in exported["input"]
    assert all("api_key" not in model for model in exported["translation"]["custom_models"])
    assert exported["translation"]["translation_max_output_tokens"] == 128
    included = yaml.safe_load(asyncio.run(config_api.export_config(include_secrets=True)).body)
    assert included == manager.get_config()
    assert included["general"]["openai_api_key"] == SECRET


@pytest.mark.parametrize("upload", [False, True])
def test_import_secretless_export_preserves_stored_secrets(config_context, upload):
    manager, request, publisher = config_context
    original = manager.get_config()
    exported = asyncio.run(config_api.export_config()).body
    if upload:
        file = UploadFile(filename="config.yaml", file=io.BytesIO(exported))
        result = asyncio.run(config_api.import_config_file(request, file))
        assert result["data"] == mask_secrets(manager.get_config())
    else:
        result = asyncio.run(config_api.import_config(yaml.safe_load(exported), request))
    assert result["success"] is True
    assert manager.get_config() == original
    event_name, payload = publisher.await_args.args
    assert event_name == "config.imported"
    assert payload["config"] == mask_secrets(original)


@pytest.mark.parametrize("wrapped", [False, True])
def test_import_masked_config_keeps_keys(config_context, wrapped):
    manager, request, publisher = config_context
    original = manager.get_config()
    incoming = mask_secrets(original)
    if wrapped:
        incoming = {"content": yaml.safe_dump(incoming, allow_unicode=True)}
    asyncio.run(config_api.import_config(incoming, request))
    assert manager.get_config() == original
    assert publisher.await_args.args[1]["config"] == mask_secrets(original)


def test_reset_response_and_event_are_masked(config_context, monkeypatch):
    manager, request, publisher = config_context
    defaults = copy.deepcopy(manager.DEFAULT_CONFIG)
    defaults["general"]["openai_api_key"] = SECRET
    monkeypatch.setattr(manager, "DEFAULT_CONFIG", defaults)
    result = asyncio.run(config_api.reset_config(request))
    assert result["data"] == mask_secrets(manager.get_config())
    assert result["data"]["general"]["openai_api_key"].startswith("••••")
    event_name, payload = publisher.await_args.args
    assert event_name == "config.reset"
    assert payload["config"] == result["data"]


def test_connection_restores_masked_key_before_calling_provider(config_context, monkeypatch):
    manager, _, _ = config_context
    called = {}

    def create_client(**kwargs):
        called.update(kwargs)
        return SimpleNamespace(models=SimpleNamespace(list=lambda: []))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=create_client))
    masked_key = mask_secrets(manager.get_config())["translation"]["openai_api_key"]
    result = asyncio.run(config_api.test_connection(config_api.TestConnectionRequest(
        backend="gpt", api_key=masked_key,
    )))
    assert result["success"] is True
    assert called["api_key"] == SECRET
