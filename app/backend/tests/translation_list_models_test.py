"""Cloud model listing; no real provider requests."""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import HTTPException
from backend.api import translation


def invoke(monkeypatch, backend, responses=(), saved=None, incoming=None):
    manager = MagicMock()
    manager.get_config.return_value = saved or {"translation": {"openai_api_key": "secret-key", "google_api_key": "secret-key"}}
    monkeypatch.setattr(translation, "get_config_manager", lambda: manager)
    client = AsyncMock()
    client.get.side_effect = responses
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=client)
    context.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=context)
    monkeypatch.setattr(httpx, "AsyncClient", factory)
    result = asyncio.run(translation.list_models(translation.ListModelsRequest(backend=backend, config=incoming or {})))
    return result, client, factory, manager


def response(data, status=200):
    return httpx.Response(status, json=data, request=httpx.Request("GET", "https://provider.test/models?key=secret-key"))


def test_gpt_models(monkeypatch):
    result, client, factory, manager = invoke(monkeypatch, "gpt", [response({"data": [{"id": "z"}, {"id": "a"}]})],
        incoming={"translation": {"gpt_base_url": "https://provider.test/v1/", "processing_proxy": "http://proxy.test"}})
    assert result == {"models": ["a", "z"]}
    assert client.get.call_args.args == ("https://provider.test/v1/models",)
    assert client.get.call_args.kwargs["headers"] == {"Authorization": "Bearer secret-key"}
    factory.assert_called_once_with(timeout=10.0, proxy="http://proxy.test")
    assert "gpt_base_url" not in manager.get_config.return_value["translation"]


def test_gemini_paging_filter_prefix(monkeypatch):
    result, client, factory, _ = invoke(monkeypatch, "gemini", [
        response({"models": [{"name": "models/z", "supportedGenerationMethods": ["generateContent"]},
                             {"name": "models/embedding", "supportedGenerationMethods": ["embedContent"]}], "nextPageToken": "next"}),
        response({"models": [{"name": "models/a", "supportedGenerationMethods": ["generateContent"]}]})],
        incoming={"translation": {"processing_proxy": "http://proxy.test"}})
    assert result == {"models": ["a", "z"]}
    assert client.get.call_args_list[1].kwargs["params"] == {"key": "secret-key", "pageToken": "next"}
    factory.assert_called_once_with(timeout=10.0)


@pytest.mark.parametrize("backend", ["gpt", "gemini"])
def test_missing_key(monkeypatch, backend):
    with pytest.raises(HTTPException) as error:
        invoke(monkeypatch, backend, saved={"translation": {}})
    assert error.value.status_code == 400


@pytest.mark.parametrize("backend", ["gpt", "gemini"])
def test_upstream_error_hides_key(monkeypatch, backend):
    with pytest.raises(HTTPException) as error:
        invoke(monkeypatch, backend, [response({"error": "secret-key"}, 500)])
    assert error.value.status_code == 502
    assert "secret-key" not in error.value.detail


def test_gemini_page_limit(monkeypatch):
    result, client, _, _ = invoke(monkeypatch, "gemini", [response({"models": [], "nextPageToken": "more"}) for _ in range(5)])
    assert result == {"models": []}
    assert client.get.call_count == 5
