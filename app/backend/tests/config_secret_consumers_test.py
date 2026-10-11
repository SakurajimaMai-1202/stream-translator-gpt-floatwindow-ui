import asyncio
import copy

from backend.core.app_sync import AppSyncBroker
from backend.core.config_manager import ConfigManager
from backend.core.config_secrets import mask_secrets


def test_sync_broker_masks_config_without_changing_source():
    payload = {'config': {'translation': {'openai_api_key': 'stored-openai-secret'},
                          'input': {'cookies_by_site': {'youtube': 'private-cookie-path'}}}}
    original = copy.deepcopy(payload)

    async def publish():
        broker = AppSyncBroker()
        queue = await broker.subscribe()
        try:
            await broker.publish('config.updated', payload)
            return queue.get_nowait()
        finally:
            await broker.unsubscribe(queue)

    event = asyncio.run(publish())
    assert event['payload']['config'] == mask_secrets(payload['config'])
    assert payload == original


def test_preview_restores_saved_family_endpoint_key(tmp_path, monkeypatch):
    from backend.api import translation as api
    manager = ConfigManager(tmp_path / 'settings.yaml')
    manager.update_config({'translation': {
        'backend': 'localllm', 'translation_model_family': 'index_translate',
        'index_translate_provider': 'lm_studio',
        'index_translate_lm_studio_model': 'Index-Translate-2B',
        'index_translate_lm_studio_api_key': 'stored-family-secret'}})
    original = copy.deepcopy(manager.get_config())
    monkeypatch.setattr(api, 'get_config_manager', lambda: manager)
    request = api.FamilyPreviewRequest(config=mask_secrets(original))
    assert api._resolve_preview_args(request)['openai_api_key'] == 'stored-family-secret'
    assert manager.get_config() == original


def test_gemini_connection_restores_masked_key(tmp_path, monkeypatch):
    import httpx
    from backend.api import translation as api
    manager = ConfigManager(tmp_path / 'settings.yaml')
    manager.update_config({'translation': {'google_api_key': 'stored-google-secret'}})
    monkeypatch.setattr(api, 'get_config_manager', lambda: manager)
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers):
            assert url.endswith('/gemini-2.5-flash-lite')
            observed = headers['x-goog-api-key']
            assert observed == 'stored-google-secret'
            return httpx.Response(200)

    monkeypatch.setattr(httpx, 'AsyncClient', FakeClient)
    masked = mask_secrets(manager.get_config())['translation']['google_api_key']
    result = asyncio.run(api.test_gemini(api.GeminiConnectionTest(api_key=masked)))
    assert result['success'] is True
